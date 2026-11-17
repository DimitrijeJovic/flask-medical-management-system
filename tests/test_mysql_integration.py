"""
Real MySQL integration tests.

These tests need a MySQL 8 server. They use, in order:
  1. a server already listening on DB_HOST:DB_PORT (default 127.0.0.1:3306), or
  2. a throwaway server started from the binary named in MYSQLD_BIN (or `mysqld` on PATH),
     with its data directory under the system temp folder.
If neither is available, every test in this module is reported as SKIPPED, never as passed.

All work happens in the database named by MYSQL_TEST_DB (default dom_zdravlja_integration_test).
Its tables are truncated before each test, so the name must contain "test".
"""
import os
import sys
import time
import shutil
import socket
import tempfile
import unittest
import threading
import subprocess
from werkzeug.security import generate_password_hash
import mysql.connector

# Ensure project root is in sys.path
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from app import app
from db import get_db_connection


def is_port_open(host, port, timeout=1.0):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(timeout)
        try:
            s.connect((host, port))
            return True
        except (socket.timeout, ConnectionRefusedError, OSError):
            return False


class MySQLServerManager:
    """Manages an isolated MySQL 8.0 server process if one is not already running."""
    _proc = None
    _started_by_suite = False
    port = int(os.environ.get("DB_PORT", "3306"))
    host = os.environ.get("DB_HOST", "127.0.0.1")
    user = os.environ.get("DB_USER", "root")
    password = os.environ.get("DB_PASSWORD", "")
    db_name = os.environ.get("MYSQL_TEST_DB", "dom_zdravlja_integration_test")
    data_dir = os.path.join(tempfile.gettempdir(), "mysql_integration_test_data")
    mysqld_bin = os.environ.get("MYSQLD_BIN") or shutil.which("mysqld")

    @classmethod
    def start_if_needed(cls):
        if "test" not in cls.db_name.lower():
            raise RuntimeError(
                f"Refusing to run: MYSQL_TEST_DB '{cls.db_name}' must contain 'test' because its tables are truncated."
            )

        if is_port_open(cls.host, cls.port):
            return

        if not cls.mysqld_bin or not os.path.exists(cls.mysqld_bin):
            raise unittest.SkipTest(
                f"No MySQL server on {cls.host}:{cls.port} and no mysqld binary found. "
                "Start a MySQL 8 server or set MYSQLD_BIN to the mysqld executable."
            )

        # Initialize data directory if not already initialized
        if not os.path.exists(cls.data_dir) or not os.listdir(cls.data_dir):
            os.makedirs(cls.data_dir, exist_ok=True)
            init_cmd = [cls.mysqld_bin, f"--datadir={cls.data_dir}", "--initialize-insecure", "--console"]
            res = subprocess.run(init_cmd, capture_output=True, text=True)
            if res.returncode != 0:
                raise RuntimeError(f"Failed to initialize isolated MySQL datadir: {res.stderr}")

        # Start isolated mysqld process
        start_cmd = [
            cls.mysqld_bin,
            f"--datadir={cls.data_dir}",
            f"--port={cls.port}",
            "--console"
        ]
        cls._proc = subprocess.Popen(start_cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        cls._started_by_suite = True

        # Wait for port to open
        deadline = time.time() + 10.0
        while time.time() < deadline:
            if is_port_open(cls.host, cls.port):
                break
            time.sleep(0.5)

        if not is_port_open(cls.host, cls.port):
            cls.stop()
            raise RuntimeError(f"Timed out waiting for MySQL server on port {cls.port}")

    @classmethod
    def stop(cls):
        if cls._proc and cls._started_by_suite:
            # On Windows, mysqld runs as a monitor process plus a server child; terminating the
            # monitor orphans the child. A SQL SHUTDOWN stops both.
            try:
                conn = mysql.connector.connect(host=cls.host, port=cls.port, user=cls.user, password=cls.password)
                conn.cursor().execute("SHUTDOWN")
                conn.close()
            except Exception:
                pass
            deadline = time.time() + 15.0
            while time.time() < deadline and is_port_open(cls.host, cls.port):
                time.sleep(0.5)
            try:
                cls._proc.terminate()
                cls._proc.wait(timeout=5)
            except Exception:
                try:
                    cls._proc.kill()
                except Exception:
                    pass
            cls._proc = None
            cls._started_by_suite = False

    @classmethod
    def init_database(cls):
        conn = mysql.connector.connect(
            host=cls.host,
            port=cls.port,
            user=cls.user,
            password=cls.password
        )
        cursor = conn.cursor(buffered=True)
        cursor.execute("SHOW DATABASES;")
        databases = [row[0] for row in cursor.fetchall()]

        if cls.db_name not in databases:
            cursor.execute(
                f"CREATE DATABASE {cls.db_name} CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;"
            )
        conn.commit()
        cursor.close()
        conn.close()

        # Connect to db_name and verify tables
        conn = mysql.connector.connect(
            host=cls.host,
            port=cls.port,
            user=cls.user,
            password=cls.password,
            database=cls.db_name
        )
        cursor = conn.cursor(buffered=True)
        cursor.execute("SHOW TABLES;")
        tables = [row[0] for row in cursor.fetchall()]

        if not tables:
            # Apply schema.sql
            schema_path = os.path.join(PROJECT_ROOT, "schema.sql")
            with open(schema_path, "r", encoding="utf-8") as f:
                schema_sql = f.read()

            for statement in schema_sql.split(";"):
                stmt = statement.strip()
                if stmt:
                    cursor.execute(stmt)
            conn.commit()

        cursor.close()
        conn.close()


class TestMySQLIntegration(unittest.TestCase):
    """
    Real MySQL Integration & Concurrency Test Suite.
    Executes against the isolated database named by MYSQL_TEST_DB (see the module docstring).
    """

    skip_reason = None

    @classmethod
    def setUpClass(cls):
        try:
            MySQLServerManager.start_if_needed()
        except unittest.SkipTest as exc:
            # Recorded here and raised per test in setUp, so each test is reported as skipped.
            cls.skip_reason = str(exc)
            return
        MySQLServerManager.init_database()

        # Configure environment for Flask application to point to the isolated test database
        os.environ["TESTING"] = "1"
        os.environ["FLASK_ENV"] = "testing"
        os.environ["DB_HOST"] = MySQLServerManager.host
        os.environ["DB_PORT"] = str(MySQLServerManager.port)
        os.environ["DB_NAME"] = MySQLServerManager.db_name
        os.environ["DB_USER"] = MySQLServerManager.user
        os.environ["DB_PASSWORD"] = MySQLServerManager.password

        app.config["TESTING"] = True
        app.config["WTF_CSRF_ENABLED"] = False
        app.secret_key = "integration_test_secret_key_fixed_length_value"

    @classmethod
    def tearDownClass(cls):
        MySQLServerManager.stop()

    def get_raw_connection(self):
        return mysql.connector.connect(
            host=MySQLServerManager.host,
            port=MySQLServerManager.port,
            user=MySQLServerManager.user,
            password=MySQLServerManager.password,
            database=MySQLServerManager.db_name,
            autocommit=False
        )

    def setUp(self):
        if self.skip_reason:
            self.skipTest(self.skip_reason)
        self.client = app.test_client()

        # Clean tables in dependency order
        conn = self.get_raw_connection()
        cursor = conn.cursor(buffered=True)
        cursor.execute("SET FOREIGN_KEY_CHECKS = 0;")
        cursor.execute("TRUNCATE TABLE medical_records;")
        cursor.execute("TRUNCATE TABLE appointments;")
        cursor.execute("TRUNCATE TABLE patients;")
        cursor.execute("TRUNCATE TABLE users;")
        cursor.execute("TRUNCATE TABLE departments;")
        cursor.execute("SET FOREIGN_KEY_CHECKS = 1;")
        conn.commit()

        # Seed initial test data
        hashed_pw = generate_password_hash("TestPassword123!")
        cursor.execute("INSERT INTO departments (id, naziv, opis) VALUES (1, 'Opšta praksa', 'Opšta medicina')")
        
        # Users: Admin(1), Doctor1(2), Doctor2(3), Nurse(4)
        cursor.execute(
            "INSERT INTO users (id, ime, email, password, role, department_id) VALUES "
            "(1, 'Admin Adminovic', 'admin@domzdravlja.rs', %s, 'admin', NULL),"
            "(2, 'Dr Marko Markovic', 'marko@domzdravlja.rs', %s, 'doktor', 1),"
            "(3, 'Dr Nikola Nikolic', 'nikola@domzdravlja.rs', %s, 'doktor', 1),"
            "(4, 'Sestra Jelena', 'jelena@domzdravlja.rs', %s, 'sestra', 1)",
            (hashed_pw, hashed_pw, hashed_pw, hashed_pw)
        )

        # Patients: Patient1(1), Patient2(2), Patient3(3)
        cursor.execute(
            "INSERT INTO patients (id, ime, prezime, jmbg, telefon) VALUES "
            "(1, 'Petar', 'Petrovic', '0101990710011', '060111222'),"
            "(2, 'Milan', 'Milanovic', '0202990710022', '060333444'),"
            "(3, 'Zoran', 'Zoranovic', '0303990710033', '060555666')"
        )

        # Appointments:
        # App 1: Patient 1 with Dr Marko (2), status 'zakazano'
        # App 2: Patient 2 with Dr Nikola (3), status 'zakazano'
        cursor.execute(
            "INSERT INTO appointments (id, patient_id, doctor_id, datum, status) VALUES "
            "(1, 1, 2, '2026-12-01 10:00:00', 'zakazano'),"
            "(2, 2, 3, '2026-12-01 11:00:00', 'zakazano')"
        )
        conn.commit()
        cursor.close()
        conn.close()

    # -------------------------------------------------------------------------
    # SCENARIO 1: Doctor ownership validation
    # -------------------------------------------------------------------------
    def test_01_doctor_ownership_validation(self):
        """Doctor can update only their own appointment; unauthorized doctor edit returns 403."""
        # Dr Marko (ID 2) attempts to update Dr Nikola's appointment (ID 2)
        with self.client.session_transaction() as sess:
            sess["user_id"] = 2
            sess["role"] = "doktor"
            sess["user_ime"] = "Dr Marko Markovic"

        response = self.client.post("/appointments/edit/2", data={
            "patient_id": "2",
            "doctor_id": "2",  # Attempting reassignment to self
            "datum": "2026-12-01 12:00:00",
            "status": "zakazano"
        })
        self.assertEqual(response.status_code, 403)

        # Verify DB: Appointment 2 is still assigned to Dr Nikola (3)
        conn = self.get_raw_connection()
        cur = conn.cursor(buffered=True, dictionary=True)
        cur.execute("SELECT doctor_id, status FROM appointments WHERE id = 2")
        appt = cur.fetchone()
        self.assertEqual(appt["doctor_id"], 3)
        self.assertEqual(appt["status"], "zakazano")
        cur.close()
        conn.close()

        # Dr Nikola (ID 3) updates his own appointment (ID 2) -> Allowed
        with self.client.session_transaction() as sess:
            sess["user_id"] = 3
            sess["role"] = "doktor"
            sess["user_ime"] = "Dr Nikola Nikolic"

        response_ok = self.client.post("/appointments/edit/2", data={
            "patient_id": "2",
            "doctor_id": "3",
            "datum": "2026-12-01 11:30:00",
            "status": "zavrseno"
        })
        self.assertEqual(response_ok.status_code, 302)

        conn = self.get_raw_connection()
        cur = conn.cursor(buffered=True, dictionary=True)
        cur.execute("SELECT status FROM appointments WHERE id = 2")
        self.assertEqual(cur.fetchone()["status"], "zavrseno")
        cur.close()
        conn.close()

    # -------------------------------------------------------------------------
    # SCENARIO 2: Cancelled appointment terminal status
    # -------------------------------------------------------------------------
    def test_02_cancelled_appointment_terminal_status(self):
        """Cancelled appointments cannot be reopened or transitioned to scheduled/completed."""
        conn = self.get_raw_connection()
        cur = conn.cursor(buffered=True)
        cur.execute("UPDATE appointments SET status = 'otkazano' WHERE id = 1")
        conn.commit()
        cur.close()
        conn.close()

        with self.client.session_transaction() as sess:
            sess["user_id"] = 2
            sess["role"] = "doktor"
            sess["user_ime"] = "Dr Marko Markovic"

        # Doctor attempts to reopen cancelled appointment
        response = self.client.post("/appointments/edit/1", data={
            "patient_id": "1",
            "doctor_id": "2",
            "datum": "2026-12-01 14:00:00",
            "status": "zakazano"
        }, follow_redirects=True)

        self.assertIn("trajno arhiviran i ne može se ponovo aktivirati niti menjati", response.get_data(as_text=True))

        # Verify DB status remained 'otkazano'
        conn = self.get_raw_connection()
        cur = conn.cursor(buffered=True, dictionary=True)
        cur.execute("SELECT status FROM appointments WHERE id = 1")
        self.assertEqual(cur.fetchone()["status"], "otkazano")
        cur.close()
        conn.close()

    # -------------------------------------------------------------------------
    # SCENARIO 3: Completed appointment immutability
    # -------------------------------------------------------------------------
    def test_03_completed_appointment_immutability(self):
        """Completed appointments cannot be reassigned to another doctor or patient."""
        conn = self.get_raw_connection()
        cur = conn.cursor(buffered=True)
        cur.execute("UPDATE appointments SET status = 'zavrseno' WHERE id = 1")
        conn.commit()
        cur.close()
        conn.close()

        with self.client.session_transaction() as sess:
            sess["user_id"] = 1  # Admin
            sess["role"] = "admin"
            sess["user_ime"] = "Admin Adminovic"

        # Attempt to change doctor on completed appointment (reassignment violation)
        response = self.client.post("/appointments/edit/1", data={
            "doctor_id": "3",  # Attempt reassigning from Dr Marko (2) to Dr Nikola (3)
            "datum": "2026-12-01 10:00:00",
            "status": "zavrseno"
        }, follow_redirects=True)

        self.assertIn("ne može se preraspodeliti drugom doktoru", response.get_data(as_text=True))

        # Verify DB row is unchanged
        conn = self.get_raw_connection()
        cur = conn.cursor(buffered=True, dictionary=True)
        cur.execute("SELECT patient_id, doctor_id, status FROM appointments WHERE id = 1")
        row = cur.fetchone()
        self.assertEqual(row["patient_id"], 1)
        self.assertEqual(row["doctor_id"], 2)
        self.assertEqual(row["status"], "zavrseno")
        cur.close()
        conn.close()

    # -------------------------------------------------------------------------
    # SCENARIO 4: Unauthorized medical record creation
    # -------------------------------------------------------------------------
    def test_04_unauthorized_medical_record_creation(self):
        """Doctor cannot create medical record for appointment assigned to another doctor."""
        with self.client.session_transaction() as sess:
            sess["user_id"] = 2  # Dr Marko
            sess["role"] = "doktor"
            sess["user_ime"] = "Dr Marko Markovic"

        # Dr Marko attempts to create record for Appointment 2 (assigned to Dr Nikola)
        response = self.client.post("/medical/add/2", data={
            "dijagnoza": "Hipertenzija",
            "terapija": "Lek A 10mg"
        })
        self.assertEqual(response.status_code, 403)

        # Verify no medical record was created in MySQL
        conn = self.get_raw_connection()
        cur = conn.cursor(buffered=True)
        cur.execute("SELECT COUNT(*) FROM medical_records")
        self.assertEqual(cur.fetchone()[0], 0)
        cur.close()
        conn.close()

    # -------------------------------------------------------------------------
    # SCENARIO 5: Atomic medical record creation
    # -------------------------------------------------------------------------
    def test_05_atomic_medical_record_creation(self):
        """Medical record insertion and appointment status update are committed atomically."""
        with self.client.session_transaction() as sess:
            sess["user_id"] = 2  # Dr Marko
            sess["role"] = "doktor"
            sess["user_ime"] = "Dr Marko Markovic"

        response = self.client.post("/medical/add/1", data={
            "dijagnoza": "Akutni bronhitis",
            "terapija": "Amoksicilin 500mg 3x1"
        })
        self.assertEqual(response.status_code, 302)

        # Verify atomic write in MySQL
        conn = self.get_raw_connection()
        cur = conn.cursor(buffered=True, dictionary=True)
        cur.execute("SELECT * FROM medical_records WHERE patient_id = 1")
        record = cur.fetchone()
        self.assertIsNotNone(record)
        self.assertEqual(record["doctor_id"], 2)
        self.assertEqual(record["dijagnoza"], "Akutni bronhitis")

        cur.execute("SELECT status FROM appointments WHERE id = 1")
        appt = cur.fetchone()
        self.assertEqual(appt["status"], "zavrseno")
        cur.close()
        conn.close()

    # -------------------------------------------------------------------------
    # SCENARIO 6: Transaction rollback on failure
    # -------------------------------------------------------------------------
    def test_06_transaction_rollback(self):
        """Transactional integrity ensures rollback leaves database in clean pre-transaction state."""
        conn = self.get_raw_connection()
        cur = conn.cursor(buffered=True)
        try:
            conn.start_transaction()
            cur.execute(
                "INSERT INTO medical_records (patient_id, doctor_id, dijagnoza, terapija) "
                "VALUES (1, 2, 'Simulirani zapis', 'Simulirana terapija')"
            )
            cur.execute("UPDATE appointments SET status = 'zavrseno' WHERE id = 1")
            # Explicitly rollback instead of commit
            conn.rollback()
        finally:
            cur.close()
            conn.close()

        # Verify rollback: 0 records inserted, appointment remains 'zakazano'
        conn = self.get_raw_connection()
        cur = conn.cursor(buffered=True, dictionary=True)
        cur.execute("SELECT COUNT(*) AS total FROM medical_records")
        self.assertEqual(cur.fetchone()["total"], 0)

        cur.execute("SELECT status FROM appointments WHERE id = 1")
        self.assertEqual(cur.fetchone()["status"], "zakazano")
        cur.close()
        conn.close()

    # -------------------------------------------------------------------------
    # SCENARIO 7: Multi-connection row locking (InnoDB SELECT ... FOR UPDATE)
    # -------------------------------------------------------------------------
    def test_07_multi_connection_row_locking(self):
        """Connection A locks row with FOR UPDATE; Connection B is blocked until Connection A commits."""
        conn1 = self.get_raw_connection()
        conn2 = self.get_raw_connection()

        thread_b_blocked_duration = [0.0]
        thread_b_started = threading.Event()
        thread_b_acquired = threading.Event()

        def connection_b_worker():
            cur2 = conn2.cursor(buffered=True, dictionary=True)
            thread_b_started.set()
            start_time = time.time()
            # This query blocks until conn1 commits
            cur2.execute("SELECT id, status FROM appointments WHERE id = 1 FOR UPDATE")
            rows = cur2.fetchall()
            thread_b_blocked_duration[0] = time.time() - start_time
            thread_b_acquired.set()
            conn2.commit()
            cur2.close()

        cur1 = conn1.cursor(buffered=True, dictionary=True)
        # Connection A acquires exclusive row lock
        conn1.start_transaction()
        cur1.execute("SELECT id, status FROM appointments WHERE id = 1 FOR UPDATE")
        rows1 = cur1.fetchall()
        self.assertEqual(len(rows1), 1)

        # Launch Connection B in separate thread
        t = threading.Thread(target=connection_b_worker)
        t.start()
        thread_b_started.wait()

        # Hold the lock for 0.4 seconds
        hold_time = 0.4
        time.sleep(hold_time)

        # Connection B must NOT have acquired the lock yet
        self.assertFalse(thread_b_acquired.is_set(), "Connection B should be blocked waiting for lock")

        # Connection A commits, releasing the lock
        conn1.commit()
        cur1.close()

        # Wait for thread B to complete
        t.join(timeout=3.0)
        self.assertTrue(thread_b_acquired.is_set(), "Connection B should acquire lock after Connection A commits")
        self.assertGreaterEqual(
            thread_b_blocked_duration[0],
            hold_time * 0.8,
            f"Expected Connection B to block for at least {hold_time}s, blocked for {thread_b_blocked_duration[0]:.3f}s"
        )

        conn1.close()
        conn2.close()

    # -------------------------------------------------------------------------
    # SCENARIO 8: Concurrent medical record creation race condition
    # -------------------------------------------------------------------------
    def test_08_concurrent_medical_record_creation(self):
        """Two concurrent connections race to complete the same appointment; exactly one succeeds."""
        results = []
        start_barrier = threading.Barrier(2)

        def attempt_record_creation(doctor_id, diagnosis):
            conn = self.get_raw_connection()
            cur = conn.cursor(buffered=True, dictionary=True)
            success = False
            start_barrier.wait()
            try:
                conn.start_transaction()
                # Row lock
                cur.execute("SELECT id, status FROM appointments WHERE id = 1 FOR UPDATE")
                rows = cur.fetchall()
                appt = rows[0] if rows else None
                if appt and appt["status"] == "zakazano":
                    cur.execute(
                        "INSERT INTO medical_records (patient_id, doctor_id, dijagnoza, terapija) "
                        "VALUES (1, %s, %s, 'Standardna terapija')",
                        (doctor_id, diagnosis)
                    )
                    cur.execute("UPDATE appointments SET status = 'zavrseno' WHERE id = 1")
                    conn.commit()
                    success = True
                else:
                    conn.rollback()
                    success = False
            except Exception:
                conn.rollback()
                success = False
            finally:
                cur.close()
                conn.close()
            results.append((doctor_id, success))

        t1 = threading.Thread(target=attempt_record_creation, args=(2, "Dijagnoza Dr Marko"))
        t2 = threading.Thread(target=attempt_record_creation, args=(3, "Dijagnoza Dr Nikola"))

        t1.start()
        t2.start()
        t1.join(timeout=5.0)
        t2.join(timeout=5.0)

        # Assert exactly one succeeded
        successes = [res for res in results if res[1] is True]
        failures = [res for res in results if res[1] is False]
        self.assertEqual(len(successes), 1, f"Expected exactly 1 success, got {len(successes)}")
        self.assertEqual(len(failures), 1, f"Expected exactly 1 rejection, got {len(failures)}")

        # Verify MySQL database state
        conn = self.get_raw_connection()
        cur = conn.cursor(buffered=True, dictionary=True)
        cur.execute("SELECT COUNT(*) AS total FROM medical_records WHERE patient_id = 1")
        self.assertEqual(cur.fetchone()["total"], 1)

        cur.execute("SELECT status FROM appointments WHERE id = 1")
        self.assertEqual(cur.fetchone()["status"], "zavrseno")
        cur.close()
        conn.close()

    # -------------------------------------------------------------------------
    # SCENARIO 9: Real ReBAC query execution
    # -------------------------------------------------------------------------
    def test_09_real_rebac_query_execution(self):
        """Execute real ReBAC scoped query: cancelled appointments excluded unless authored record exists."""
        conn = self.get_raw_connection()
        cur = conn.cursor(buffered=True)

        # Setup 4 distinct relationship scenarios for Dr Marko (ID 2):
        # Patient 1: Active scheduled appointment (Already exists: App 1) -> VISIBLE
        # Patient 2: Cancelled appointment only (App 3) -> NOT VISIBLE
        cur.execute("INSERT INTO appointments (id, patient_id, doctor_id, datum, status) VALUES (3, 2, 2, '2026-12-02 10:00:00', 'otkazano')")
        # Patient 3: Cancelled appointment BUT authored medical record -> VISIBLE
        cur.execute("INSERT INTO appointments (id, patient_id, doctor_id, datum, status) VALUES (4, 3, 2, '2026-12-03 10:00:00', 'otkazano')")
        cur.execute("INSERT INTO medical_records (id, patient_id, doctor_id, dijagnoza, terapija) VALUES (1, 3, 2, 'Prethodna dijagnoza', 'Terapija')")
        # Patient 4: No relationship -> NOT VISIBLE
        cur.execute("INSERT INTO patients (id, ime, prezime, jmbg, telefon) VALUES (4, 'Nenad', 'Nenadovic', '0404990710044', '060777888')")
        conn.commit()

        # Real ReBAC query from app.py
        rebac_sql = """
            SELECT p.id, p.ime, p.prezime
            FROM patients p
            WHERE EXISTS (
                SELECT 1 FROM appointments a
                WHERE a.patient_id = p.id
                  AND a.doctor_id = %s
                  AND a.status IN ('zakazano', 'zavrseno')
            )
            OR EXISTS (
                SELECT 1 FROM medical_records mr
                WHERE mr.patient_id = p.id
                  AND mr.doctor_id = %s
            )
            ORDER BY p.id ASC
        """
        cur = conn.cursor(buffered=True, dictionary=True)
        cur.execute(rebac_sql, (2, 2))
        visible_patients = cur.fetchall()
        visible_ids = [p["id"] for p in visible_patients]

        # Assert Patient 1 (scheduled) and Patient 3 (authored record) are visible
        # Assert Patient 2 (only cancelled) and Patient 4 (no relationship) are NOT visible
        self.assertIn(1, visible_ids, "Patient with scheduled appointment must be visible")
        self.assertIn(3, visible_ids, "Patient with authored medical record must be visible")
        self.assertNotIn(2, visible_ids, "Patient with only cancelled appointment must NOT be visible")
        self.assertNotIn(4, visible_ids, "Unrelated patient must NOT be visible")
        self.assertEqual(len(visible_ids), 2)

        cur.close()
        conn.close()

    # -------------------------------------------------------------------------
    # SCENARIO 10: Parent-row deletion safeguards
    # -------------------------------------------------------------------------
    def test_10_parent_row_deletion_safeguards(self):
        """Parent users and patients with medical records cannot be deleted; orphan protection verified."""
        # 1. Author a medical record for Patient 1 authored by Dr Marko (2)
        conn = self.get_raw_connection()
        cur = conn.cursor(buffered=True)
        cur.execute(
            "INSERT INTO medical_records (id, patient_id, doctor_id, dijagnoza, terapija) "
            "VALUES (1, 1, 2, 'Trajna dijagnoza', 'Trajna terapija')"
        )
        conn.commit()
        cur.close()
        conn.close()

        with self.client.session_transaction() as sess:
            sess["user_id"] = 1  # Admin
            sess["role"] = "admin"
            sess["user_ime"] = "Admin Adminovic"

        # Attempt to delete Doctor Marko (has authored medical record)
        res_user = self.client.post("/users/delete/2", follow_redirects=True)
        self.assertIn("Nije moguće obrisati lekara koji ima evidentirane medicinske izveštaje", res_user.get_data(as_text=True))

        # Verify Dr Marko still exists in MySQL users table
        conn = self.get_raw_connection()
        cur = conn.cursor(buffered=True, dictionary=True)
        cur.execute("SELECT id FROM users WHERE id = 2")
        self.assertIsNotNone(cur.fetchone(), "Doctor with authored records must not be deleted")

        # Attempt to delete Patient 1 (has medical record)
        res_patient = self.client.post("/patients/delete/1", follow_redirects=True)
        self.assertIn("Nije moguće obrisati pacijenta sa postojećim medicinskim kartonom", res_patient.get_data(as_text=True))

        # Verify Patient 1 still exists in MySQL patients table
        cur.execute("SELECT id FROM patients WHERE id = 1")
        self.assertIsNotNone(cur.fetchone(), "Patient with medical records must not be deleted")

        # Control test: Delete Patient 3 (no medical records and no appointments)
        cur.execute("DELETE FROM appointments WHERE patient_id = 3")
        cur.execute("DELETE FROM medical_records WHERE patient_id = 3")
        conn.commit()

        res_del_ok = self.client.post("/patients/delete/3", follow_redirects=True)
        cur.execute("SELECT id FROM patients WHERE id = 3")
        self.assertIsNone(cur.fetchone(), "Patient without medical records should be deletable")

        cur.close()
        conn.close()


if __name__ == "__main__":
    unittest.main()
