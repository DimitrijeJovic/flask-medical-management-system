import os
import sys
import logging
from math import ceil
from functools import wraps

from flask import Flask, render_template, request, redirect, session, flash, abort
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.middleware.proxy_fix import ProxyFix
from flask_wtf.csrf import CSRFProtect, CSRFError
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
import click

from db import get_db_connection

# Configure structured logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s'
)
security_logger = logging.getLogger("security")

app = Flask(__name__)

# Reverse proxy support (single hop by default, configurable via PROXY_FIX_HOPS)
proxy_hops = int(os.environ.get("PROXY_FIX_HOPS", "1"))
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=proxy_hops, x_proto=proxy_hops, x_host=proxy_hops)

# Secret key configuration: Module import does not raise to preserve test pattern compatibility
app.secret_key = os.environ.get("SECRET_KEY")

# CSRF Protection initialization
csrf = CSRFProtect(app)

# Rate limiting initialization (default memory:// for local/single-process, Redis in production via env)
limiter = Limiter(
    key_func=get_remote_address,
    app=app,
    default_limits=[],
    storage_uri=os.environ.get("RATELIMIT_STORAGE_URI", "memory://")
)


@app.errorhandler(CSRFError)
def handle_csrf_error(e):
    security_logger.warning("CSRF validation failed for IP %s on path %s", get_remote_address(), request.path)
    return render_template("error.html", message="CSRF provera nije uspela ili je sesija istekla. Osvežite stranicu."), 400


@app.before_request
def validate_runtime_security():
    # Enforce non-empty SECRET_KEY for all requests unless running in Flask test mode
    if not app.config.get("TESTING"):
        if not app.secret_key or app.secret_key.strip() == "" or app.secret_key == "sifra":
            raise RuntimeError("FATAL SECURITY CONFIGURATION: SECRET_KEY environment variable is missing, empty, or insecure.")


# =========================================================================
# AUTHENTICATION & AUTHORIZATION VIEW DECORATORS
# =========================================================================

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if "user_id" not in session:
            return redirect("/login")
        return f(*args, **kwargs)
    return decorated_function


def role_required(*allowed_roles):
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if "user_id" not in session:
                return redirect("/login")
            if session.get("role") not in allowed_roles:
                abort(403)
            return f(*args, **kwargs)
        return decorated_function
    return decorator


def check_doctor_patient_relationship(doctor_id, patient_id):
    """
    Checks if doctor has an active/completed appointment OR prior medical record for this patient.
    Cancelled appointments ('otkazano') explicitly DO NOT grant access.
    """
    db = get_db_connection()
    cursor = db.cursor()
    try:
        cursor.execute("""
            SELECT 1 FROM appointments
            WHERE doctor_id = %s AND patient_id = %s AND status IN ('zakazano', 'zavrseno')
            UNION
            SELECT 1 FROM medical_records
            WHERE doctor_id = %s AND patient_id = %s
            LIMIT 1
        """, (doctor_id, patient_id, doctor_id, patient_id))
        return cursor.fetchone() is not None
    finally:
        cursor.close()
        db.close()


# =========================================================================
# DASHBOARD CONTEXT HELPER
# =========================================================================

def get_dashboard_context():
    db = get_db_connection()
    cursor = db.cursor(dictionary=True)

    cursor.execute("""
        SELECT users.*, departments.naziv AS department_name
        FROM users
        LEFT JOIN departments ON users.department_id = departments.id
        WHERE users.id = %s
    """, (session["user_id"],))
    current_user = cursor.fetchone()

    cursor.execute("SELECT COUNT(*) AS total FROM patients")
    patients_count = cursor.fetchone()["total"]

    cursor.execute("SELECT COUNT(*) AS total FROM appointments")
    appointments_count = cursor.fetchone()["total"]

    cursor.execute("SELECT COUNT(*) AS total FROM users WHERE role = 'doktor'")
    doctors_count = cursor.fetchone()["total"]

    cursor.execute("SELECT COUNT(*) AS total FROM users WHERE role = 'sestra'")
    nurses_count = cursor.fetchone()["total"]

    cursor.execute("SELECT COUNT(*) AS total FROM users")
    users_count = cursor.fetchone()["total"]

    role = session["role"]
    status_filter = ""
    status_params = ()
    if role == "doktor":
        status_filter = "WHERE doctor_id = %s"
        status_params = (session["user_id"],)

    cursor.execute(f"""
        SELECT
            COUNT(CASE WHEN status = 'zakazano' THEN 1 END) AS zakazano,
            COUNT(CASE WHEN status = 'otkazano' THEN 1 END) AS otkazano,
            COUNT(CASE WHEN status = 'zavrseno' THEN 1 END) AS zavrseno
        FROM appointments
        {status_filter}
    """, status_params)
    status_counts = cursor.fetchone()

    today_filter = ""
    today_params = ()
    if role == "doktor":
        today_filter = "AND doctor_id = %s"
        today_params = (session["user_id"],)

    cursor.execute(f"""
        SELECT COUNT(*) AS total
        FROM appointments
        WHERE DATE(datum) = CURDATE()
        {today_filter}
    """, today_params)
    today_appointments_count = cursor.fetchone()["total"]

    cursor.execute(f"""
        SELECT COUNT(*) AS total
        FROM appointments
        WHERE datum >= NOW()
          AND status = 'zakazano'
          {today_filter}
    """, today_params)
    upcoming_appointments_count = cursor.fetchone()["total"]

    cursor.execute("""
        SELECT COUNT(*) AS total
        FROM patients
        WHERE telefon IS NULL OR telefon = ''
    """)
    patients_missing_phone_count = cursor.fetchone()["total"]

    if role == "doktor":
        cursor.execute("""
            SELECT COUNT(*) AS total
            FROM medical_records
            WHERE doctor_id = %s
        """, (session["user_id"],))
    else:
        cursor.execute("SELECT COUNT(*) AS total FROM medical_records")
    reports_count = cursor.fetchone()["total"]

    if role == "doktor":
        cursor.execute("""
            SELECT COUNT(DISTINCT patient_id) AS total
            FROM appointments
            WHERE doctor_id = %s
        """, (session["user_id"],))
        my_patients_count = cursor.fetchone()["total"]

        cursor.execute("""
            SELECT appointments.*, patients.ime AS patient_ime, patients.prezime
            FROM appointments
            JOIN patients ON appointments.patient_id = patients.id
            WHERE appointments.doctor_id = %s
            ORDER BY appointments.datum DESC
            LIMIT 5
        """, (session["user_id"],))
    else:
        my_patients_count = patients_count
        cursor.execute("""
            SELECT appointments.*, patients.ime AS patient_ime, patients.prezime,
                   users.ime AS doctor_ime
            FROM appointments
            JOIN patients ON appointments.patient_id = patients.id
            JOIN users ON appointments.doctor_id = users.id
            ORDER BY appointments.datum DESC
            LIMIT 5
        """)

    recent_appointments = cursor.fetchall()

    cursor.close()
    db.close()

    return {
        "dashboard_user": current_user,
        "patients_count": patients_count,
        "appointments_count": appointments_count,
        "doctors_count": doctors_count,
        "nurses_count": nurses_count,
        "users_count": users_count,
        "status_counts": status_counts,
        "my_patients_count": my_patients_count,
        "recent_appointments": recent_appointments,
        "today_appointments_count": today_appointments_count,
        "upcoming_appointments_count": upcoming_appointments_count,
        "patients_missing_phone_count": patients_missing_phone_count,
        "reports_count": reports_count,
    }


# =========================================================================
# CORE APPLICATION ROUTES
# =========================================================================

@app.route("/")
@login_required
def home():
    return render_template("dashboard.html", **get_dashboard_context())


@app.route("/login", methods=["GET", "POST"])
@limiter.limit("5 per minute", methods=["POST"])
def login():
    if "user_id" in session:
        return redirect("/")

    if request.method == "POST":
        email = request.form.get("email", "").strip()
        password = request.form.get("password", "")

        db = get_db_connection()
        cursor = db.cursor(dictionary=True)

        cursor.execute("SELECT * FROM users WHERE email = %s", (email,))
        user = cursor.fetchone()

        cursor.close()
        db.close()

        if user and check_password_hash(user["password"], password):
            session["user_id"] = user["id"]
            session["role"] = user["role"]
            session["ime"] = user["ime"]

            security_logger.info("AUTH_LOGIN_SUCCESS user_id=%s role=%s ip=%s", user["id"], user["role"], get_remote_address())
            flash("Uspesno ste se prijavili!", "success")
            return redirect("/")

        security_logger.warning("AUTH_LOGIN_FAILURE ip=%s", get_remote_address())
        flash("Pogresan email ili lozinka!", "danger")
        return redirect("/login")

    return render_template("login.html")


@app.route("/logout", methods=["POST"])
@login_required
def logout():
    user_id = session.get("user_id")
    session.clear()
    security_logger.info("AUTH_LOGOUT user_id=%s ip=%s", user_id, get_remote_address())
    flash("Uspesno ste se odjavili.", "info")
    return redirect("/login")


@app.route("/admin")
@role_required("admin")
def admin_dashboard():
    return render_template("dashboard.html", **get_dashboard_context())


@app.route("/doktor")
@role_required("doktor")
def doktor_dashboard():
    return render_template("dashboard.html", **get_dashboard_context())


@app.route("/sestra")
@role_required("sestra")
def sestra_dashboard():
    return render_template("dashboard.html", **get_dashboard_context())


# =========================================================================
# USER MANAGEMENT (ADMIN ONLY)
# =========================================================================

@app.route("/users")
@role_required("admin")
def users():
    db = get_db_connection()
    cursor = db.cursor(dictionary=True)

    cursor.execute("""
        SELECT users.*, departments.naziv AS department_name
        FROM users
        LEFT JOIN departments ON users.department_id = departments.id
        ORDER BY role, ime
    """)
    user_list = cursor.fetchall()

    cursor.close()
    db.close()

    return render_template("users.html", users=user_list)


@app.route("/users/add", methods=["GET", "POST"])
@role_required("admin")
def add_user():
    db = get_db_connection()
    cursor = db.cursor(dictionary=True)

    if request.method == "POST":
        ime = request.form.get("ime", "").strip()
        email = request.form.get("email", "").strip()
        password = request.form.get("password", "")
        role = request.form.get("role", "")
        department_id = request.form.get("department_id", "").strip() or None

        if not ime or not email or not password or not role:
            flash("Sva obavezna polja moraju biti popunjena.", "danger")
            cursor.close()
            db.close()
            return redirect("/users/add")

        if role not in ("admin", "doktor", "sestra"):
            flash("Izabrana uloga nije validna.", "danger")
            cursor.close()
            db.close()
            return redirect("/users/add")

        if len(password) < 8:
            flash("Lozinka mora imati najmanje 8 karaktera.", "danger")
            cursor.close()
            db.close()
            return redirect("/users/add")

        try:
            cursor.execute("""
                INSERT INTO users (ime, email, password, role, department_id)
                VALUES (%s, %s, %s, %s, %s)
            """, (ime, email, generate_password_hash(password), role, department_id))
            db.commit()

            security_logger.info("USER_CREATED admin_id=%s created_email=%s role=%s", session["user_id"], email, role)
            flash("Korisnik uspesno kreiran!", "success")
            return redirect("/users")
        except Exception:
            db.rollback()
            flash("Korisnik sa tom email adresom već postoji ili je došlo do greške.", "danger")
            return redirect("/users/add")
        finally:
            cursor.close()
            db.close()

    cursor.execute("SELECT * FROM departments ORDER BY naziv")
    departments = cursor.fetchall()
    cursor.close()
    db.close()

    return render_template("add_user.html", departments=departments)


@app.route("/users/delete/<int:id>", methods=["POST"])
@role_required("admin")
def delete_user(id):
    if id == session["user_id"]:
        flash("Ne mozete obrisati svoj nalog!", "danger")
        return redirect("/users")

    db = get_db_connection()
    cursor = db.cursor(dictionary=True)
    try:
        db.start_transaction()

        # 1. Lock the parent user row
        cursor.execute("SELECT id, role FROM users WHERE id = %s FOR UPDATE", (id,))
        target_user = cursor.fetchone()
        if not target_user:
            db.rollback()
            flash("Korisnik nije pronadjen.", "danger")
            return redirect("/users")

        # 2. Application-level safeguard: Check if user authored medical records
        cursor.execute("SELECT COUNT(*) AS total FROM medical_records WHERE doctor_id = %s FOR UPDATE", (id,))
        if cursor.fetchone()["total"] > 0:
            db.rollback()
            flash("Nije moguće obrisati lekara koji ima evidentirane medicinske izveštaje. Istorija lečenja mora ostati sačuvana.", "danger")
            return redirect("/users")

        # 3. Application-level safeguard: Check if user has associated appointments
        cursor.execute("SELECT COUNT(*) AS total FROM appointments WHERE doctor_id = %s FOR UPDATE", (id,))
        if cursor.fetchone()["total"] > 0:
            db.rollback()
            flash("Nije moguće obrisati lekara koji ima zakazane ili realizovane preglede. Pregledi moraju biti reasocirani.", "danger")
            return redirect("/users")

        # 4. Safe delete
        cursor.execute("DELETE FROM users WHERE id = %s", (id,))
        db.commit()

        security_logger.info("USER_DELETED admin_id=%s deleted_user_id=%s", session["user_id"], id)
        flash("Korisnik uspesno obrisan!", "success")
    except Exception:
        db.rollback()
        security_logger.error("Error deleting user %s", id, exc_info=True)
        flash("Došlo je do greške prilikom brisanja korisnika.", "danger")
    finally:
        cursor.close()
        db.close()

    return redirect("/users")


# =========================================================================
# PATIENT MANAGEMENT
# =========================================================================

@app.route("/patients")
@role_required("admin", "sestra", "doktor")
def patients():
    db = get_db_connection()
    cursor = db.cursor(dictionary=True)

    search = request.args.get("search", "").strip()
    page = max(int(request.args.get("page", 1)), 1)
    limit = 8
    offset = (page - 1) * limit

    if search:
        search_term = f"%{search}%"
        cursor.execute("""
            SELECT COUNT(*) AS total
            FROM patients
            WHERE ime LIKE %s OR prezime LIKE %s OR jmbg LIKE %s
        """, (search_term, search_term, search_term))
        total_patients = cursor.fetchone()["total"]

        cursor.execute("""
            SELECT *
            FROM patients
            WHERE ime LIKE %s OR prezime LIKE %s OR jmbg LIKE %s
            ORDER BY prezime, ime
            LIMIT %s OFFSET %s
        """, (search_term, search_term, search_term, limit, offset))
    else:
        cursor.execute("SELECT COUNT(*) AS total FROM patients")
        total_patients = cursor.fetchone()["total"]

        cursor.execute("""
            SELECT *
            FROM patients
            ORDER BY prezime, ime
            LIMIT %s OFFSET %s
        """, (limit, offset))

    patient_list = cursor.fetchall()
    total_pages = max(ceil(total_patients / limit), 1)

    cursor.close()
    db.close()

    return render_template(
        "patients.html",
        patients=patient_list,
        search=search,
        page=page,
        total_pages=total_pages,
        total_patients=total_patients,
    )


@app.route("/patients/add", methods=["GET", "POST"])
@role_required("admin", "sestra")
def add_patient():
    if request.method == "POST":
        ime = request.form.get("ime", "").strip()
        prezime = request.form.get("prezime", "").strip()
        jmbg = request.form.get("jmbg", "").strip()
        telefon = request.form.get("telefon", "").strip()

        if not ime or not prezime:
            flash("Ime i prezime su obavezni!", "danger")
            return redirect("/patients/add")

        if len(jmbg) != 13 or not jmbg.isdigit():
            flash("JMBG mora imati tačno 13 cifara!", "danger")
            return redirect("/patients/add")

        db = get_db_connection()
        cursor = db.cursor()

        try:
            cursor.execute("""
                INSERT INTO patients (ime, prezime, jmbg, telefon)
                VALUES (%s, %s, %s, %s)
            """, (ime, prezime, jmbg, telefon))
            db.commit()

            security_logger.info("PATIENT_ADDED staff_id=%s jmbg_suffix=%s", session["user_id"], jmbg[-4:])
            flash("Pacijent uspesno dodat!", "success")
            return redirect("/patients")
        except Exception:
            db.rollback()
            flash("Pacijent sa unetim JMBG-om već postoji.", "danger")
            return redirect("/patients/add")
        finally:
            cursor.close()
            db.close()

    return render_template("add_patient.html")


@app.route("/patients/edit/<int:id>", methods=["GET", "POST"])
@role_required("admin", "sestra")
def edit_patient(id):
    db = get_db_connection()
    cursor = db.cursor(dictionary=True)

    if request.method == "POST":
        ime = request.form.get("ime", "").strip()
        prezime = request.form.get("prezime", "").strip()
        jmbg = request.form.get("jmbg", "").strip()
        telefon = request.form.get("telefon", "").strip()

        if not ime or not prezime:
            flash("Ime i prezime su obavezni!", "danger")
            cursor.close()
            db.close()
            return redirect(f"/patients/edit/{id}")

        if len(jmbg) != 13 or not jmbg.isdigit():
            flash("JMBG mora imati tačno 13 cifara!", "danger")
            cursor.close()
            db.close()
            return redirect(f"/patients/edit/{id}")

        try:
            cursor.execute("""
                UPDATE patients
                SET ime = %s, prezime = %s, jmbg = %s, telefon = %s
                WHERE id = %s
            """, (ime, prezime, jmbg, telefon, id))
            db.commit()

            flash("Podaci o pacijentu su uspesno izmenjeni!", "success")
            return redirect("/patients")
        except Exception:
            db.rollback()
            flash("Pacijent sa unetim JMBG-om već postoji ili je došlo do greške.", "danger")
            return redirect(f"/patients/edit/{id}")
        finally:
            cursor.close()
            db.close()

    cursor.execute("SELECT * FROM patients WHERE id = %s", (id,))
    patient = cursor.fetchone()
    cursor.close()
    db.close()

    if not patient:
        flash("Pacijent nije pronadjen.", "danger")
        return redirect("/patients")

    return render_template("edit_patient.html", patient=patient)


@app.route("/patients/delete/<int:id>", methods=["POST"])
@role_required("admin")
def delete_patient(id):
    db = get_db_connection()
    cursor = db.cursor(dictionary=True)
    try:
        db.start_transaction()

        # 1. Lock the parent patient row
        cursor.execute("SELECT id FROM patients WHERE id = %s FOR UPDATE", (id,))
        patient = cursor.fetchone()
        if not patient:
            db.rollback()
            flash("Pacijent nije pronadjen.", "danger")
            return redirect("/patients")

        # 2. Application-level safeguard: Check for medical records
        cursor.execute("SELECT COUNT(*) AS total FROM medical_records WHERE patient_id = %s FOR UPDATE", (id,))
        if cursor.fetchone()["total"] > 0:
            db.rollback()
            flash("Nije moguće obrisati pacijenta sa postojećim medicinskim kartonom radi očuvanja integriteta podataka.", "danger")
            return redirect("/patients")

        # 3. Application-level safeguard: Check for appointment history
        cursor.execute("SELECT COUNT(*) AS total FROM appointments WHERE patient_id = %s FOR UPDATE", (id,))
        if cursor.fetchone()["total"] > 0:
            db.rollback()
            flash("Nije moguće obrisati pacijenta koji ima evidentirane preglede. Istorija zakazivanja mora biti sačuvana.", "danger")
            return redirect("/patients")

        # 4. Safe delete (orphaned record with zero dependencies)
        cursor.execute("DELETE FROM patients WHERE id = %s", (id,))
        db.commit()

        security_logger.info("PATIENT_DELETED admin_id=%s patient_id=%s", session["user_id"], id)
        flash("Pacijent uspesno obrisan!", "warning")
    except Exception:
        db.rollback()
        security_logger.error("Error deleting patient %s", id, exc_info=True)
        flash("Došlo je do greške prilikom brisanja pacijenta.", "danger")
    finally:
        cursor.close()
        db.close()

    return redirect("/patients")


# =========================================================================
# APPOINTMENT MANAGEMENT
# =========================================================================

@app.route("/appointments")
@login_required
def appointments():
    db = get_db_connection()
    cursor = db.cursor(dictionary=True)

    role = session["role"]
    if role == "doktor":
        cursor.execute("""
            SELECT appointments.*, patients.ime AS patient_ime, patients.prezime AS patient_prezime,
                   users.ime AS doctor_ime
            FROM appointments
            JOIN patients ON appointments.patient_id = patients.id
            JOIN users ON appointments.doctor_id = users.id
            WHERE appointments.doctor_id = %s
            ORDER BY datum DESC
        """, (session["user_id"],))
    else:
        cursor.execute("""
            SELECT appointments.*, patients.ime AS patient_ime, patients.prezime AS patient_prezime,
                   users.ime AS doctor_ime
            FROM appointments
            JOIN patients ON appointments.patient_id = patients.id
            JOIN users ON appointments.doctor_id = users.id
            ORDER BY datum DESC
        """)

    appointment_list = cursor.fetchall()
    cursor.close()
    db.close()

    return render_template("appointments.html", appointments=appointment_list)


@app.route("/appointments/add", methods=["GET", "POST"])
@role_required("sestra", "admin")
def add_appointment():
    db = get_db_connection()
    cursor = db.cursor(dictionary=True)

    if request.method == "POST":
        patient_id = request.form.get("patient_id")
        doctor_id = request.form.get("doctor_id")
        datum = request.form.get("datum", "").strip()

        if not patient_id or not doctor_id or not datum:
            flash("Sva polja moraju biti popunjena!", "danger")
            cursor.close()
            db.close()
            return redirect("/appointments/add")

        try:
            cursor.execute("""
                INSERT INTO appointments (patient_id, doctor_id, datum, status)
                VALUES (%s, %s, %s, 'zakazano')
            """, (patient_id, doctor_id, datum))
            db.commit()

            security_logger.info("APPOINTMENT_SCHEDULED staff_id=%s patient_id=%s doctor_id=%s", session["user_id"], patient_id, doctor_id)
            flash("Pregled uspesno zakazan!", "success")
            return redirect("/appointments")
        except Exception:
            db.rollback()
            flash("Došlo je do greške prilikom zakazivanja pregleda.", "danger")
            return redirect("/appointments/add")
        finally:
            cursor.close()
            db.close()

    cursor.execute("SELECT * FROM patients ORDER BY prezime, ime")
    patients = cursor.fetchall()

    cursor.execute("SELECT * FROM users WHERE role = 'doktor' ORDER BY ime")
    doctors = cursor.fetchall()

    cursor.close()
    db.close()

    return render_template("add_appointment.html", patients=patients, doctors=doctors)


@app.route("/appointments/edit/<int:id>", methods=["GET", "POST"])
@role_required("admin", "doktor", "sestra")
def edit_appointment(id):
    db = get_db_connection()
    cursor = db.cursor(dictionary=True)

    cursor.execute("SELECT * FROM appointments WHERE id = %s", (id,))
    appointment = cursor.fetchone()

    if not appointment:
        cursor.close()
        db.close()
        flash("Pregled nije pronadjen.", "danger")
        return redirect("/appointments")

    # DOCTOR OWNERSHIP CHECK: Doctor can only edit appointments assigned to them
    if session["role"] == "doktor" and appointment["doctor_id"] != session["user_id"]:
        cursor.close()
        db.close()
        abort(403)

    if request.method == "POST":
        datum = request.form.get("datum", "").strip()
        status = request.form.get("status", "").strip()

        if not datum or not status:
            flash("Datum i status su obavezni!", "danger")
            cursor.close()
            db.close()
            return redirect(f"/appointments/edit/{id}")

        if status not in ("zakazano", "zavrseno", "otkazano"):
            flash("Nevalidan status pregleda.", "danger")
            cursor.close()
            db.close()
            return redirect(f"/appointments/edit/{id}")

        # DOCTOR RESTRICTION: Doctors cannot reassign doctor_id or patient_id
        if session["role"] == "doktor":
            new_doctor_id = appointment["doctor_id"]
        else:
            new_doctor_id = request.form.get("doctor_id", appointment["doctor_id"])

        try:
            cursor.execute("""
                UPDATE appointments
                SET datum = %s, status = %s, doctor_id = %s
                WHERE id = %s
            """, (datum, status, new_doctor_id, id))
            db.commit()

            flash("Pregled uspesno izmenjen!", "success")
            return redirect("/appointments")
        except Exception:
            db.rollback()
            flash("Došlo je do greške prilikom izmene pregleda.", "danger")
            return redirect(f"/appointments/edit/{id}")
        finally:
            cursor.close()
            db.close()

    cursor.execute("SELECT * FROM users WHERE role = 'doktor' ORDER BY ime")
    doctors = cursor.fetchall()
    cursor.close()
    db.close()

    return render_template("edit_appointment.html", appointment=appointment, doctors=doctors)


# =========================================================================
# MEDICAL RECORDS & CLINICAL HISTORY
# =========================================================================

@app.route("/medical/<int:patient_id>")
@login_required
def medical_records(patient_id):
    role = session.get("role")
    user_id = session.get("user_id")

    # NURSE IS FORBIDDEN
    if role == "sestra":
        security_logger.warning("MEDICAL_RECORD_DENIED_NURSE nurse_id=%s patient_id=%s", user_id, patient_id)
        abort(403)

    db = get_db_connection()
    cursor = db.cursor(dictionary=True)

    cursor.execute("SELECT * FROM patients WHERE id = %s", (patient_id,))
    patient = cursor.fetchone()

    if not patient:
        cursor.close()
        db.close()
        abort(404)

    # DOCTOR RELATIONSHIP VERIFICATION
    if role == "doktor":
        if not check_doctor_patient_relationship(user_id, patient_id):
            cursor.close()
            db.close()
            security_logger.warning("MEDICAL_RECORD_DENIED_NO_RELATIONSHIP doctor_id=%s patient_id=%s", user_id, patient_id)
            abort(403)

    security_logger.info("MEDICAL_RECORD_READ user_id=%s role=%s patient_id=%s", user_id, role, patient_id)

    cursor.execute("""
        SELECT users.ime AS doctor_ime, departments.naziv AS department_name
        FROM appointments
        JOIN users ON appointments.doctor_id = users.id
        LEFT JOIN departments ON users.department_id = departments.id
        WHERE appointments.patient_id = %s
        ORDER BY appointments.datum DESC
        LIMIT 1
    """, (patient_id,))
    assigned_doctor = cursor.fetchone()

    cursor.execute("""
        SELECT medical_records.*, users.ime AS doctor_ime,
               departments.naziv AS department_name
        FROM medical_records
        JOIN users ON medical_records.doctor_id = users.id
        LEFT JOIN departments ON users.department_id = departments.id
        WHERE patient_id = %s
        ORDER BY datum DESC
    """, (patient_id,))
    records = cursor.fetchall()

    cursor.close()
    db.close()

    return render_template(
        "medical_records.html",
        patient=patient,
        assigned_doctor=assigned_doctor,
        records=records,
    )


@app.route("/medical/add/<int:appointment_id>", methods=["GET", "POST"])
@role_required("doktor")
def add_medical_record(appointment_id):
    db = get_db_connection()
    cursor = db.cursor(dictionary=True)

    cursor.execute("SELECT * FROM appointments WHERE id = %s", (appointment_id,))
    appointment = cursor.fetchone()

    if not appointment:
        cursor.close()
        db.close()
        abort(404)

    # DOCTOR OWNERSHIP & STATUS INTEGRITY
    if appointment["doctor_id"] != session["user_id"]:
        cursor.close()
        db.close()
        security_logger.warning("MEDICAL_RECORD_ADD_DENIED_UNOWNED doctor_id=%s app_id=%s", session["user_id"], appointment_id)
        abort(403)

    if appointment["status"] == "otkazano":
        cursor.close()
        db.close()
        flash("Nije moguće dodati izveštaj za otkazan pregled.", "danger")
        return redirect("/appointments")

    if request.method == "POST":
        dijagnoza = request.form.get("dijagnoza", "").strip()
        terapija = request.form.get("terapija", "").strip()

        if not dijagnoza:
            flash("Dijagnoza je obavezna!", "danger")
            cursor.close()
            db.close()
            return render_template("add_medical.html", appointment_id=appointment_id)

        try:
            # ZERO TRUST: patient_id is derived exclusively from the verified appointment in DB
            verified_patient_id = appointment["patient_id"]
            author_doctor_id = session["user_id"]

            cursor.execute("""
                INSERT INTO medical_records (patient_id, doctor_id, dijagnoza, terapija)
                VALUES (%s, %s, %s, %s)
            """, (verified_patient_id, author_doctor_id, dijagnoza, terapija))

            cursor.execute("""
                UPDATE appointments
                SET status = 'zavrseno'
                WHERE id = %s
            """, (appointment_id,))

            db.commit()
            security_logger.info("MEDICAL_RECORD_CREATED doctor_id=%s patient_id=%s app_id=%s", author_doctor_id, verified_patient_id, appointment_id)
            flash("Izvestaj uspesno dodat!", "success")
            return redirect("/appointments")
        except Exception:
            db.rollback()
            flash("Došlo je do greške prilikom unosa izveštaja.", "danger")
            return redirect("/appointments")
        finally:
            cursor.close()
            db.close()

    cursor.close()
    db.close()
    return render_template("add_medical.html", appointment_id=appointment_id)


@app.route("/medical/edit/<int:id>", methods=["GET", "POST"])
@role_required("doktor", "admin")
def edit_medical_record(id):
    db = get_db_connection()
    cursor = db.cursor(dictionary=True)
    try:
        cursor.execute("SELECT * FROM medical_records WHERE id = %s", (id,))
        record = cursor.fetchone()

        if not record:
            abort(404)

        # DOCTOR OWNERSHIP: Doctors can only edit their own authored reports
        if session.get("role") != "admin" and record.get("doctor_id") != session.get("user_id"):
            abort(403)

        if request.method == "POST":
            dijagnoza = request.form.get("dijagnoza", "").strip()
            terapija = request.form.get("terapija", "").strip()

            if not dijagnoza:
                flash("Dijagnoza ne može biti prazna!", "danger")
                return render_template("edit_medical.html", record=record)

            cursor.execute("""
                UPDATE medical_records
                SET dijagnoza = %s, terapija = %s
                WHERE id = %s
            """, (dijagnoza, terapija, id))
            db.commit()

            security_logger.info("MEDICAL_RECORD_UPDATED actor_id=%s record_id=%s", session["user_id"], id)
            flash("Izvestaj izmenjen!", "success")
            return redirect(f"/medical/{record['patient_id']}")

        return render_template("edit_medical.html", record=record)
    finally:
        cursor.close()
        db.close()


@app.route("/medical/delete/<int:id>", methods=["POST"])
@role_required("doktor", "admin")
def delete_medical_record(id):
    db = get_db_connection()
    cursor = db.cursor(dictionary=True)
    try:
        cursor.execute("SELECT * FROM medical_records WHERE id = %s", (id,))
        record = cursor.fetchone()

        if not record:
            abort(404)

        # DOCTOR OWNERSHIP: Doctor can only delete their own record
        if session.get("role") != "admin" and record.get("doctor_id") != session.get("user_id"):
            abort(403)

        cursor.execute("DELETE FROM medical_records WHERE id = %s", (id,))
        db.commit()

        security_logger.info("MEDICAL_RECORD_DELETED actor_id=%s record_id=%s", session["user_id"], id)
        flash("Izvestaj obrisan!", "warning")
        return redirect(f"/medical/{record['patient_id']}")
    finally:
        cursor.close()
        db.close()


# =========================================================================
# SECURE CLI BOOTSTRAP (flask create-admin)
# =========================================================================

@app.cli.command("create-admin")
def create_admin():
    """One-time, fail-closed bootstrap operation for the initial system administrator."""
    db = None
    cursor = None
    try:
        db = get_db_connection()
        cursor = db.cursor(dictionary=True)

        cursor.execute("SELECT COUNT(*) AS total FROM users WHERE role = 'admin'")
        if cursor.fetchone()["total"] > 0:
            raise click.ClickException("Error: An administrator already exists. Bootstrap aborted.")

        ime = click.prompt("Enter Admin Full Name")
        email = click.prompt("Enter Admin Email")

        cursor.execute("SELECT COUNT(*) AS total FROM users WHERE email = %s", (email.strip(),))
        if cursor.fetchone()["total"] > 0:
            raise click.ClickException("Error: A user with this email address already exists.")

        password = click.prompt("Enter Admin Password", hide_input=True, confirmation_prompt=True)
        if len(password) < 8:
            raise click.ClickException("Error: Password must be at least 8 characters.")

        cursor.execute("""
            INSERT INTO users (ime, email, password, role)
            VALUES (%s, %s, %s, 'admin')
        """, (ime.strip(), email.strip(), generate_password_hash(password)))
        db.commit()
        click.echo("Administrator successfully created.")
    except Exception as e:
        if db:
            try:
                db.rollback()
            except Exception:
                pass
        if isinstance(e, click.ClickException):
            raise e
        raise click.ClickException(f"Fatal error during administrator bootstrap: {e}")
    finally:
        if cursor:
            try:
                cursor.close()
            except Exception:
                pass
        if db:
            try:
                db.close()
            except Exception:
                pass


# Local development entry point
if __name__ == "__main__":
    debug_mode = os.environ.get("FLASK_DEBUG", "0").lower() in ("1", "true")
    if not app.secret_key and not app.config.get("TESTING"):
        raise RuntimeError("FATAL SECURITY CONFIGURATION: SECRET_KEY environment variable must be set.")
    app.run(host="127.0.0.1", port=int(os.environ.get("PORT", 5000)), debug=debug_mode)
