import unittest
from unittest.mock import MagicMock, patch, call
from werkzeug.security import generate_password_hash
from click.testing import CliRunner

import app as medical_app


class MedicalSystemSecurityTestCase(unittest.TestCase):
    def setUp(self):
        medical_app.app.config["TESTING"] = True
        medical_app.app.config["SECRET_KEY"] = "test-secret-key-32-bytes-minimum-entropy!!"
        medical_app.app.config["WTF_CSRF_ENABLED"] = False  # Disabled by default in tests unless explicitly testing CSRF
        self.client = medical_app.app.test_client()
        self.runner = medical_app.app.test_cli_runner()

    # =========================================================================
    # 1. AUTHENTICATION & REGISTRATION DECOMMISSIONING
    # =========================================================================

    def test_public_register_route_is_removed_404(self):
        """Public registration route must return 404 Not Found."""
        response = self.client.get("/register")
        self.assertEqual(response.status_code, 404)

        post_response = self.client.post("/register", data={"role": "admin"})
        self.assertEqual(post_response.status_code, 404)

    def test_anonymous_redirected_to_login(self):
        """Anonymous requests to protected endpoints must redirect to /login."""
        protected_urls = ["/", "/admin", "/doktor", "/sestra", "/users", "/users/add", "/patients", "/appointments"]
        for url in protected_urls:
            response = self.client.get(url, follow_redirects=False)
            self.assertEqual(response.status_code, 302, f"Expected redirect for {url}")
            self.assertIn("/login", response.headers["Location"], f"Expected redirect to /login for {url}")

    def test_logout_clears_session_post_only(self):
        """Logout must be POST-only, reject GET with 405, and clear session on POST."""
        with self.client.session_transaction() as sess:
            sess["user_id"] = 1
            sess["role"] = "admin"
            sess["ime"] = "Admin Test"

        # GET must be rejected with 405 Method Not Allowed
        get_response = self.client.get("/logout")
        self.assertEqual(get_response.status_code, 405)

        # POST must succeed
        post_response = self.client.post("/logout", follow_redirects=False)
        self.assertEqual(post_response.status_code, 302)
        self.assertIn("/login", post_response.headers["Location"])

        with self.client.session_transaction() as sess:
            self.assertNotIn("user_id", sess)
            self.assertNotIn("role", sess)

    # =========================================================================
    # 2. ROLE-BASED ACCESS CONTROL (RBAC) & USER CREATION
    # =========================================================================

    def test_nurse_cannot_access_admin_or_users(self):
        """Nurses must receive HTTP 403 when accessing administrative endpoints."""
        with self.client.session_transaction() as sess:
            sess["user_id"] = 2
            sess["role"] = "sestra"
            sess["ime"] = "Sestra Test"

        for url in ["/admin", "/users", "/users/add"]:
            response = self.client.get(url, follow_redirects=False)
            self.assertEqual(response.status_code, 403, f"Expected 403 Forbidden for {url}")

    def test_doctor_cannot_access_admin_or_users(self):
        """Doctors must receive HTTP 403 when accessing administrative endpoints."""
        with self.client.session_transaction() as sess:
            sess["user_id"] = 3
            sess["role"] = "doktor"
            sess["ime"] = "Dr Test"

        for url in ["/admin", "/users", "/users/add"]:
            response = self.client.get(url, follow_redirects=False)
            self.assertEqual(response.status_code, 403, f"Expected 403 Forbidden for {url}")

    @patch("app.get_db_connection")
    def test_admin_can_create_staff_user(self, mock_db_conn):
        """Admin can create new staff users via /users/add with password hashing."""
        mock_cursor = MagicMock()
        mock_conn = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        mock_db_conn.return_value = mock_conn

        with self.client.session_transaction() as sess:
            sess["user_id"] = 1
            sess["role"] = "admin"
            sess["ime"] = "Admin Test"

        response = self.client.post("/users/add", data={
            "ime": "Novi Doktor",
            "email": "novi.doktor@domzdravlja.rs",
            "password": "SecurePassword123!",
            "role": "doktor",
            "department_id": "1"
        }, follow_redirects=False)

        self.assertEqual(response.status_code, 302)
        self.assertIn("/users", response.headers["Location"])
        mock_conn.commit.assert_called_once()

    # =========================================================================
    # 3. CLI BOOTSTRAP (flask create-admin)
    # =========================================================================

    @patch("app.get_db_connection")
    def test_cli_create_admin_success(self, mock_db_conn):
        """create-admin CLI command creates initial admin when none exists."""
        mock_cursor = MagicMock()
        mock_cursor.fetchone.side_effect = [{"total": 0}, {"total": 0}]  # 0 admins, 0 existing emails
        mock_conn = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        mock_db_conn.return_value = mock_conn

        result = self.runner.invoke(medical_app.create_admin, input="Root Admin\nadmin@domzdravlja.rs\nAdminPass123!\nAdminPass123!\n")
        self.assertEqual(result.exit_code, 0)
        self.assertIn("Administrator successfully created.", result.output)
        mock_conn.commit.assert_called_once()

    @patch("app.get_db_connection")
    def test_cli_create_admin_refuses_when_admin_exists(self, mock_db_conn):
        """create-admin CLI command fails with non-zero exit code if admin already exists."""
        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = {"total": 1}  # Admin exists
        mock_conn = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        mock_db_conn.return_value = mock_conn

        result = self.runner.invoke(medical_app.create_admin)
        self.assertNotEqual(result.exit_code, 0)
        self.assertIn("Error: An administrator already exists.", result.output)
        mock_conn.commit.assert_not_called()

    # =========================================================================
    # 4. MEDICAL RECORD AUTHORIZATION & IDOR MITIGATION
    # =========================================================================

    def test_nurse_cannot_view_patient_medical_records(self):
        """Nurses must receive HTTP 403 when trying to access /medical/<patient_id>."""
        with self.client.session_transaction() as sess:
            sess["user_id"] = 2
            sess["role"] = "sestra"
            sess["ime"] = "Sestra Test"

        response = self.client.get("/medical/10")
        self.assertEqual(response.status_code, 403)

    @patch("app.get_db_connection")
    def test_unrelated_doctor_cannot_view_patient_medical_records(self, mock_db_conn):
        """Doctor without appointment or historical record receives HTTP 403."""
        mock_cursor = MagicMock()
        mock_conn = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        mock_db_conn.return_value = mock_conn

        # Patient exists
        mock_cursor.fetchone.side_effect = [
            {"id": 10, "ime": "Petar", "prezime": "Petrovic"},  # SELECT * FROM patients
            None  # check_doctor_patient_relationship returns None
        ]

        with self.client.session_transaction() as sess:
            sess["user_id"] = 3
            sess["role"] = "doktor"
            sess["ime"] = "Dr Test"

        response = self.client.get("/medical/10")
        self.assertEqual(response.status_code, 403)

    @patch("app.get_db_connection")
    def test_doctor_with_scheduled_appointment_can_view_medical_records(self, mock_db_conn):
        """Doctor with an active scheduled appointment can view medical records."""
        mock_cursor = MagicMock()
        mock_conn = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        mock_db_conn.return_value = mock_conn

        mock_cursor.fetchone.side_effect = [
            {"id": 10, "ime": "Petar", "prezime": "Petrovic", "jmbg": "1234567890123", "telefon": "060123456"},
            {"1": 1},  # check_doctor_patient_relationship returns active link
            {"doctor_ime": "Dr Test", "department_name": "Opsta praksa"},  # assigned doctor
        ]
        mock_cursor.fetchall.return_value = []

        with self.client.session_transaction() as sess:
            sess["user_id"] = 3
            sess["role"] = "doktor"
            sess["ime"] = "Dr Test"

        response = self.client.get("/medical/10")
        self.assertEqual(response.status_code, 200)

    # =========================================================================
    # 5. MEDICAL RECORD CREATION & APPOINTMENT INTEGRITY
    # =========================================================================

    @patch("app.get_db_connection")
    def test_doctor_cannot_create_record_for_another_doctors_appointment(self, mock_db_conn):
        """Doctor cannot create medical record for an appointment assigned to another doctor."""
        mock_cursor = MagicMock()
        mock_conn = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        mock_db_conn.return_value = mock_conn

        # Appointment belongs to doctor_id = 99
        mock_cursor.fetchone.return_value = {
            "id": 5,
            "patient_id": 10,
            "doctor_id": 99,
            "status": "zakazano"
        }

        # Current doctor is user_id = 3
        with self.client.session_transaction() as sess:
            sess["user_id"] = 3
            sess["role"] = "doktor"
            sess["ime"] = "Dr Test"

        response = self.client.post("/medical/add/5", data={
            "dijagnoza": "Grip",
            "terapija": "Mirovanje"
        })
        self.assertEqual(response.status_code, 403)
        mock_conn.commit.assert_not_called()

    @patch("app.get_db_connection")
    def test_doctor_cannot_create_record_for_cancelled_appointment(self, mock_db_conn):
        """Doctor cannot create a record for a cancelled appointment."""
        mock_cursor = MagicMock()
        mock_conn = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        mock_db_conn.return_value = mock_conn

        mock_cursor.fetchone.return_value = {
            "id": 5,
            "patient_id": 10,
            "doctor_id": 3,
            "status": "otkazano"
        }

        with self.client.session_transaction() as sess:
            sess["user_id"] = 3
            sess["role"] = "doktor"
            sess["ime"] = "Dr Test"

        response = self.client.post("/medical/add/5", data={
            "dijagnoza": "Grip",
            "terapija": "Mirovanje"
        }, follow_redirects=False)

        self.assertEqual(response.status_code, 302)
        self.assertIn("/appointments", response.headers["Location"])
        mock_conn.commit.assert_not_called()

    @patch("app.get_db_connection")
    def test_medical_record_add_derives_patient_from_appointment_not_form(self, mock_db_conn):
        """Submitted patient_id or doctor_id form fields are ignored; IDs derived from DB appointment."""
        mock_cursor = MagicMock()
        mock_conn = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        mock_db_conn.return_value = mock_conn

        # Appointment in DB belongs to patient 10 and doctor 3
        mock_cursor.fetchone.return_value = {
            "id": 5,
            "patient_id": 10,
            "doctor_id": 3,
            "status": "zakazano"
        }

        with self.client.session_transaction() as sess:
            sess["user_id"] = 3
            sess["role"] = "doktor"
            sess["ime"] = "Dr Test"

        # Client attempts to spoof patient_id=999 and doctor_id=888
        response = self.client.post("/medical/add/5", data={
            "patient_id": "999",
            "doctor_id": "888",
            "dijagnoza": "Bronhitis",
            "terapija": "Antibiotik"
        }, follow_redirects=False)

        self.assertEqual(response.status_code, 302)
        # Verify that SQL INSERT used verified patient 10 and authenticated doctor 3
        insert_call = mock_cursor.execute.call_args_list[1]
        insert_args = insert_call[0][1]
        self.assertEqual(insert_args[0], 10, "patient_id must be derived from verified appointment (10)")
        self.assertEqual(insert_args[1], 3, "doctor_id must come from authenticated session (3)")

    # =========================================================================
    # 6. DESTRUCTIVE OPERATIONS & CASCADE SAFEGUARDS
    # =========================================================================

    def test_destructive_routes_reject_get_with_405(self):
        """All deletion endpoints must be POST-only and return 405 on GET."""
        with self.client.session_transaction() as sess:
            sess["user_id"] = 1
            sess["role"] = "admin"
            sess["ime"] = "Admin Test"

        endpoints = ["/users/delete/2", "/patients/delete/1", "/medical/delete/1"]
        for endpoint in endpoints:
            response = self.client.get(endpoint)
            self.assertEqual(response.status_code, 405, f"Expected 405 Method Not Allowed for GET {endpoint}")

    @patch("app.get_db_connection")
    def test_doctor_deletion_blocked_when_medical_records_exist(self, mock_db_conn):
        """Doctor cannot be deleted if they authored medical records; records preserved."""
        mock_cursor = MagicMock()
        mock_conn = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        mock_db_conn.return_value = mock_conn

        mock_cursor.fetchone.side_effect = [
            {"id": 3, "role": "doktor"},  # Target user exists
            {"total": 5}                   # 5 authored medical records exist
        ]

        with self.client.session_transaction() as sess:
            sess["user_id"] = 1
            sess["role"] = "admin"
            sess["ime"] = "Admin Test"

        response = self.client.post("/users/delete/3", follow_redirects=False)
        self.assertEqual(response.status_code, 302)
        self.assertIn("/users", response.headers["Location"])
        mock_conn.rollback.assert_called_once()
        mock_conn.commit.assert_not_called()

    @patch("app.get_db_connection")
    def test_doctor_deletion_blocked_when_appointments_exist(self, mock_db_conn):
        """Doctor cannot be deleted if they have associated appointments."""
        mock_cursor = MagicMock()
        mock_conn = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        mock_db_conn.return_value = mock_conn

        mock_cursor.fetchone.side_effect = [
            {"id": 3, "role": "doktor"},  # Target user exists
            {"total": 0},                  # 0 medical records
            {"total": 3}                   # 3 appointments exist
        ]

        with self.client.session_transaction() as sess:
            sess["user_id"] = 1
            sess["role"] = "admin"
            sess["ime"] = "Admin Test"

        response = self.client.post("/users/delete/3", follow_redirects=False)
        self.assertEqual(response.status_code, 302)
        mock_conn.rollback.assert_called_once()
        mock_conn.commit.assert_not_called()

    @patch("app.get_db_connection")
    def test_patient_deletion_blocked_when_medical_records_exist(self, mock_db_conn):
        """Patient with medical records cannot be deleted; clinical history preserved."""
        mock_cursor = MagicMock()
        mock_conn = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        mock_db_conn.return_value = mock_conn

        mock_cursor.fetchone.side_effect = [
            {"id": 10},   # Patient exists
            {"total": 2}  # 2 medical records exist
        ]

        with self.client.session_transaction() as sess:
            sess["user_id"] = 1
            sess["role"] = "admin"
            sess["ime"] = "Admin Test"

        response = self.client.post("/patients/delete/10", follow_redirects=False)
        self.assertEqual(response.status_code, 302)
        self.assertIn("/patients", response.headers["Location"])
        mock_conn.rollback.assert_called_once()
        mock_conn.commit.assert_not_called()

    @patch("app.get_db_connection")
    def test_patient_deletion_blocked_when_appointments_exist(self, mock_db_conn):
        """Patient with appointments (even 0 medical records) cannot be deleted."""
        mock_cursor = MagicMock()
        mock_conn = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        mock_db_conn.return_value = mock_conn

        mock_cursor.fetchone.side_effect = [
            {"id": 10},   # Patient exists
            {"total": 0},  # 0 medical records
            {"total": 1}   # 1 appointment exists
        ]

        with self.client.session_transaction() as sess:
            sess["user_id"] = 1
            sess["role"] = "admin"
            sess["ime"] = "Admin Test"

        response = self.client.post("/patients/delete/10", follow_redirects=False)
        self.assertEqual(response.status_code, 302)
        mock_conn.rollback.assert_called_once()
        mock_conn.commit.assert_not_called()

    # =========================================================================
    # 7. CSRF PROTECTION & PRODUCTION CONFIGURATION
    # =========================================================================

    def test_post_without_csrf_token_returns_400_when_csrf_enabled(self):
        """When CSRF is enabled, POST request without csrf_token returns HTTP 400 Bad Request."""
        medical_app.app.config["WTF_CSRF_ENABLED"] = True
        try:
            response = self.client.post("/login", data={
                "email": "test@domzdravlja.rs",
                "password": "Password123!"
            })
            self.assertEqual(response.status_code, 400)
            self.assertIn(b"CSRF", response.data)
        finally:
            medical_app.app.config["WTF_CSRF_ENABLED"] = False

    def test_runtime_secret_key_validation_raises_in_production(self):
        """Runtime configuration check must raise RuntimeError if SECRET_KEY is missing/insecure in production."""
        medical_app.app.config["TESTING"] = False
        original_secret = medical_app.app.secret_key
        try:
            # Empty secret
            medical_app.app.secret_key = ""
            with self.assertRaises(RuntimeError):
                medical_app.validate_runtime_security()

            # Insecure default "sifra"
            medical_app.app.secret_key = "sifra"
            with self.assertRaises(RuntimeError):
                medical_app.validate_runtime_security()
        finally:
            medical_app.app.config["TESTING"] = True
            medical_app.app.secret_key = original_secret

    def test_wsgi_startup_validation_rejects_missing_secret(self):
        """wsgi.py must raise RuntimeError at startup if SECRET_KEY is missing or insecure."""
        import importlib
        import os
        old_env = os.environ.get("SECRET_KEY")
        try:
            os.environ["SECRET_KEY"] = "sifra"
            with self.assertRaises(RuntimeError):
                import wsgi
                importlib.reload(wsgi)

            os.environ["SECRET_KEY"] = ""
            with self.assertRaises(RuntimeError):
                import wsgi
                importlib.reload(wsgi)
        finally:
            if old_env is not None:
                os.environ["SECRET_KEY"] = old_env
            else:
                os.environ.pop("SECRET_KEY", None)


if __name__ == "__main__":
    unittest.main()
