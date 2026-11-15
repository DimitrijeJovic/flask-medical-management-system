import os
from math import ceil

from flask import Flask, render_template, request, redirect, session, flash
from werkzeug.security import generate_password_hash, check_password_hash

from db import get_db_connection

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "sifra")


def login_required():
    return "user_id" in session


def role_required(*roles):
    return login_required() and session.get("role") in roles


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


@app.route("/")
def home():
    if not login_required():
        return redirect("/login")

    return render_template("dashboard.html", **get_dashboard_context())


@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        ime = request.form["ime"].strip()
        email = request.form["email"].strip()
        password = request.form["password"]
        role = request.form["role"]

        db = get_db_connection()
        cursor = db.cursor()

        try:
            cursor.execute("""
                INSERT INTO users (ime, email, password, role)
                VALUES (%s, %s, %s, %s)
            """, (ime, email, generate_password_hash(password), role))

            db.commit()
            flash("Registracija uspesna!", "success")
            return redirect("/login")
        except Exception:
            db.rollback()
            flash("Email vec postoji!", "danger")
            return redirect("/register")
        finally:
            cursor.close()
            db.close()

    return render_template("register.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if login_required():
        return redirect("/")

    if request.method == "POST":
        email = request.form["email"].strip()
        password = request.form["password"]

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

            flash("Uspesno ste se prijavili!", "success")
            return redirect("/")

        flash("Pogresan email ili lozinka!", "danger")
        return redirect("/login")

    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    return redirect("/login")


@app.route("/admin")
def admin_dashboard():
    if not role_required("admin"):
        return redirect("/login")

    return render_template("dashboard.html", **get_dashboard_context())


@app.route("/doktor")
def doktor_dashboard():
    if not role_required("doktor"):
        return redirect("/login")

    return render_template("dashboard.html", **get_dashboard_context())


@app.route("/sestra")
def sestra_dashboard():
    if not role_required("sestra"):
        return redirect("/login")

    return render_template("dashboard.html", **get_dashboard_context())


@app.route("/users")
def users():
    if not role_required("admin"):
        return redirect("/login")

    db = get_db_connection()
    cursor = db.cursor(dictionary=True)

    cursor.execute("SELECT * FROM users ORDER BY role, ime")
    users = cursor.fetchall()

    cursor.close()
    db.close()

    return render_template("users.html", users=users)


@app.route("/users/delete/<int:id>")
def delete_user(id):
    if not role_required("admin"):
        return redirect("/login")

    if id == session["user_id"]:
        flash("Ne mozete obrisati svoj nalog!", "danger")
        return redirect("/users")

    db = get_db_connection()
    cursor = db.cursor()

    cursor.execute("DELETE FROM appointments WHERE doctor_id = %s", (id,))
    cursor.execute("DELETE FROM users WHERE id = %s", (id,))
    db.commit()

    cursor.close()
    db.close()

    flash("Korisnik uspesno obrisan!", "success")
    return redirect("/users")


@app.route("/patients")
def patients():
    if not role_required("admin", "sestra", "doktor"):
        return redirect("/login")

    db = get_db_connection()
    cursor = db.cursor(dictionary=True)

    search = request.args.get("search", "").strip()
    page = max(int(request.args.get("page", 1)), 1)
    limit = 8
    offset = (page - 1) * limit

    query = """
        SELECT DISTINCT patients.*
        FROM patients
    """
    count_query = """
        SELECT COUNT(DISTINCT patients.id) AS total
        FROM patients
    """

    params = []
    count_params = []

    if session["role"] == "doktor":
        doctor_filter = """
            JOIN appointments ON patients.id = appointments.patient_id
            WHERE appointments.doctor_id = %s
        """
        query += doctor_filter
        count_query += doctor_filter
        params.append(session["user_id"])
        count_params.append(session["user_id"])

        if search:
            query += " AND (patients.ime LIKE %s OR patients.prezime LIKE %s)"
            count_query += " AND (patients.ime LIKE %s OR patients.prezime LIKE %s)"
            params.extend([f"%{search}%", f"%{search}%"])
            count_params.extend([f"%{search}%", f"%{search}%"])
    elif search:
        query += " WHERE patients.ime LIKE %s OR patients.prezime LIKE %s"
        count_query += " WHERE patients.ime LIKE %s OR patients.prezime LIKE %s"
        params.extend([f"%{search}%", f"%{search}%"])
        count_params.extend([f"%{search}%", f"%{search}%"])

    cursor.execute(count_query, tuple(count_params))
    total_patients = cursor.fetchone()["total"]
    total_pages = max(ceil(total_patients / limit), 1)

    if page > total_pages:
        page = total_pages
        offset = (page - 1) * limit

    query += " ORDER BY patients.prezime, patients.ime LIMIT %s OFFSET %s"
    params.extend([limit, offset])

    cursor.execute(query, tuple(params))
    patients = cursor.fetchall()

    cursor.close()
    db.close()

    return render_template(
        "patients.html",
        patients=patients,
        page=page,
        total_pages=total_pages,
        total_patients=total_patients,
    )


@app.route("/patients/add", methods=["GET", "POST"])
def add_patient():
    if not role_required("admin", "sestra"):
        return redirect("/login")

    if request.method == "POST":
        ime = request.form["ime"].strip()
        prezime = request.form["prezime"].strip()
        jmbg = request.form["jmbg"].strip()
        telefon = request.form["telefon"].strip()

        if not ime or not prezime:
            flash("Ime i prezime su obavezni!", "danger")
            return redirect("/patients/add")

        db = get_db_connection()
        cursor = db.cursor()

        cursor.execute("""
            INSERT INTO patients (ime, prezime, jmbg, telefon)
            VALUES (%s, %s, %s, %s)
        """, (ime, prezime, jmbg, telefon))
        db.commit()

        cursor.close()
        db.close()

        flash("Pacijent uspesno dodat!", "success")
        return redirect("/patients")

    return render_template("add_patient.html")


@app.route("/patients/edit/<int:id>", methods=["GET", "POST"])
def edit_patient(id):
    if not role_required("admin", "sestra"):
        return redirect("/patients")

    db = get_db_connection()
    cursor = db.cursor(dictionary=True)

    if request.method == "POST":
        ime = request.form["ime"].strip()
        prezime = request.form["prezime"].strip()
        telefon = request.form["telefon"].strip()

        cursor.execute("""
            UPDATE patients
            SET ime = %s, prezime = %s, telefon = %s
            WHERE id = %s
        """, (ime, prezime, telefon, id))

        db.commit()
        cursor.close()
        db.close()

        flash("Pacijent izmenjen!", "success")
        return redirect("/patients")

    cursor.execute("SELECT * FROM patients WHERE id = %s", (id,))
    patient = cursor.fetchone()

    cursor.close()
    db.close()

    if not patient:
        flash("Pacijent nije pronadjen.", "danger")
        return redirect("/patients")

    return render_template("edit_patient.html", patient=patient)


@app.route("/patients/delete/<int:id>")
def delete_patient(id):
    if not role_required("admin"):
        return redirect("/patients")

    db = get_db_connection()
    cursor = db.cursor()

    cursor.execute("DELETE FROM patients WHERE id = %s", (id,))
    db.commit()

    cursor.close()
    db.close()

    flash("Pacijent uspesno obrisan!", "warning")
    return redirect("/patients")


@app.route("/appointments")
def appointments():
    if not login_required():
        return redirect("/login")

    db = get_db_connection()
    cursor = db.cursor(dictionary=True)

    if session["role"] == "doktor":
        cursor.execute("""
            SELECT appointments.*, patients.ime AS patient_ime, patients.prezime,
                   users.ime AS doctor_ime
            FROM appointments
            JOIN patients ON appointments.patient_id = patients.id
            JOIN users ON appointments.doctor_id = users.id
            WHERE appointments.doctor_id = %s
            ORDER BY appointments.datum DESC
        """, (session["user_id"],))
    else:
        cursor.execute("""
            SELECT appointments.*, patients.ime AS patient_ime, patients.prezime,
                   users.ime AS doctor_ime
            FROM appointments
            JOIN patients ON appointments.patient_id = patients.id
            JOIN users ON appointments.doctor_id = users.id
            ORDER BY appointments.datum DESC
        """)

    appointments = cursor.fetchall()

    cursor.close()
    db.close()

    return render_template("appointments.html", appointments=appointments)


@app.route("/appointments/add", methods=["GET", "POST"])
def add_appointment():
    if not role_required("sestra"):
        return redirect("/appointments")

    db = get_db_connection()
    cursor = db.cursor(dictionary=True)

    if request.method == "POST":
        patient_id = request.form["patient_id"]
        doctor_id = request.form["doctor_id"]
        datum = request.form["datum"]

        cursor.execute("""
            INSERT INTO appointments (patient_id, doctor_id, datum)
            VALUES (%s, %s, %s)
        """, (patient_id, doctor_id, datum))

        db.commit()
        cursor.close()
        db.close()

        flash("Pregled uspesno zakazan!", "success")
        return redirect("/appointments")

    cursor.execute("SELECT * FROM patients ORDER BY prezime, ime")
    patients = cursor.fetchall()

    cursor.execute("SELECT * FROM users WHERE role = 'doktor' ORDER BY ime")
    doctors = cursor.fetchall()

    cursor.close()
    db.close()

    return render_template("add_appointment.html", patients=patients, doctors=doctors)


@app.route("/appointments/edit/<int:id>", methods=["GET", "POST"])
def edit_appointment(id):
    if not role_required("admin", "doktor"):
        return redirect("/appointments")

    db = get_db_connection()
    cursor = db.cursor(dictionary=True)

    cursor.execute("SELECT * FROM appointments WHERE id = %s", (id,))
    appointment = cursor.fetchone()

    if not appointment:
        cursor.close()
        db.close()
        flash("Pregled nije pronadjen.", "danger")
        return redirect("/appointments")

    if request.method == "POST":
        datum = request.form["datum"]
        status = request.form["status"]

        cursor.execute("""
            UPDATE appointments
            SET datum = %s, status = %s
            WHERE id = %s
        """, (datum, status, id))

        db.commit()
        cursor.close()
        db.close()

        flash("Pregled izmenjen!", "success")
        return redirect("/appointments")

    cursor.close()
    db.close()

    return render_template("edit_appointment.html", appointment=appointment)


@app.route("/medical/<int:patient_id>")
def medical_records(patient_id):
    if not login_required():
        return redirect("/login")

    db = get_db_connection()
    cursor = db.cursor(dictionary=True)

    cursor.execute("""
        SELECT patients.*
        FROM patients
        WHERE id = %s
    """, (patient_id,))
    patient = cursor.fetchone()

    if not patient:
        cursor.close()
        db.close()
        flash("Pacijent nije pronadjen.", "danger")
        return redirect("/patients")

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
def add_medical_record(appointment_id):
    if not role_required("doktor"):
        return redirect("/appointments")

    db = get_db_connection()
    cursor = db.cursor(dictionary=True)

    cursor.execute("SELECT * FROM appointments WHERE id = %s", (appointment_id,))
    appointment = cursor.fetchone()

    if not appointment:
        cursor.close()
        db.close()
        flash("Pregled nije pronadjen.", "danger")
        return redirect("/appointments")

    if request.method == "POST":
        dijagnoza = request.form["dijagnoza"]
        terapija = request.form["terapija"]

        cursor.execute("""
            INSERT INTO medical_records (patient_id, doctor_id, dijagnoza, terapija)
            VALUES (%s, %s, %s, %s)
        """, (appointment["patient_id"], session["user_id"], dijagnoza, terapija))

        cursor.execute("""
            UPDATE appointments
            SET status = 'zavrseno'
            WHERE id = %s
        """, (appointment_id,))

        db.commit()
        cursor.close()
        db.close()

        flash("Izvestaj uspesno dodat!", "success")
        return redirect("/appointments")

    cursor.close()
    db.close()

    return render_template("add_medical.html", appointment_id=appointment_id)


@app.route("/medical/edit/<int:id>", methods=["GET", "POST"])
def edit_medical_record(id):
    if not role_required("doktor"):
        return redirect("/patients")

    db = get_db_connection()
    cursor = db.cursor(dictionary=True)

    cursor.execute("SELECT * FROM medical_records WHERE id = %s", (id,))
    record = cursor.fetchone()

    if not record:
        cursor.close()
        db.close()
        flash("Izvestaj nije pronadjen.", "danger")
        return redirect("/patients")

    if request.method == "POST":
        dijagnoza = request.form["dijagnoza"]
        terapija = request.form["terapija"]

        cursor.execute("""
            UPDATE medical_records
            SET dijagnoza = %s, terapija = %s
            WHERE id = %s
        """, (dijagnoza, terapija, id))

        db.commit()
        cursor.close()
        db.close()

        flash("Izvestaj izmenjen!", "success")
        return redirect(f"/medical/{record['patient_id']}")

    cursor.close()
    db.close()

    return render_template("edit_medical.html", record=record)


@app.route("/medical/delete/<int:id>")
def delete_medical_record(id):
    if not role_required("doktor"):
        return redirect("/patients")

    db = get_db_connection()
    cursor = db.cursor(dictionary=True)

    cursor.execute("SELECT * FROM medical_records WHERE id = %s", (id,))
    record = cursor.fetchone()

    if not record:
        cursor.close()
        db.close()
        return redirect("/patients")

    cursor.execute("DELETE FROM medical_records WHERE id = %s", (id,))
    db.commit()

    cursor.close()
    db.close()

    flash("Izvestaj obrisan!", "danger")
    return redirect(f"/medical/{record['patient_id']}")


if __name__ == "__main__":
    app.run(debug=True)
