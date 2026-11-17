# Healthcare Management System (Dom Zdravlja)

A secure, role-based outpatient healthcare and clinical management web application built with Python, Flask, MySQL, and Bootstrap 5.

Developed to demonstrate enterprise-grade web development patterns: relational database modeling, role-based and relationship-based access control (RBAC & ReBAC), application-level cascade deletion safeguards, longitudinal medical record retention, server-side session invalidation, and defensive security hardening against OWASP Top 10 vulnerabilities.

---

## 1. Problem Statement

Outpatient health centers and primary care clinics require strict compartmentalization of administrative, medical, and nursing functions. Unrestricted record access or accidental administrative deletions can lead to severe privacy breaches or irreversible clinical data loss.

This system provides a centralized clinical workflow portal ensuring:
- Medical history cannot be permanently deleted by any user or administrator.
- Clinical notes are accessible exclusively to doctors with an active or historical professional relationship with the patient.
- Administrative operations cannot alter diagnostic findings or compromise relational integrity.
- Real-time session validation prevents privilege persistence after role demotion or account deletion.

---

## 2. Main Application Features

- **Clinical Queue Management:** Real-time scheduling, tracking, and status progression of patient appointments (`zakazano` $\rightarrow$ `zavrseno` or `otkazano`).
- **Electronic Medical Records (EMR):** Structured diagnostic reports and therapy entries authored directly during outpatient consultations.
- **Terminal Status Auditing:** Cancelled appointments remain permanent historical records and cannot be reopened or manipulated.
- **Scoped Patient Directory:** Context-sensitive patient search preventing unauthorized bulk patient enumeration or identity data exposure.
- **Fail-Closed Administration:** Protected staff user provisioning, department assignments, and interactive CLI bootstrap.

---

## 3. User Roles & Permission Matrix

The application strictly separates responsibilities across three distinct staff roles:

| Capability / Route | Administrator (`admin`) | Doctor (`doktor`) | Nurse (`sestra`) |
|---|---|---|---|
| Staff Management (`/users`, `/users/add`) | Full CRUD (excluding hard deletes of doctors with records) | Forbidden (403) | Forbidden (403) |
| Patient Directory (`/patients`) | Full View & Search (All Patients) | Scoped View (Active appointments or authored records) | Full View & Search (All Patients) |
| Patient Creation & Demographics (`/patients/add`) | Allowed | Forbidden (403) | Allowed |
| Appointment Scheduling (`/appointments/add`) | Allowed | Forbidden (403) | Allowed |
| Appointment Consultation & Updates (`/appointments/edit`) | Allowed (Pending reassignments) | Own Appointments Only (Cannot reassign or reopen) | Allowed (Pending reassignments) |
| EMR History Read (`/medical/<patient_id>`) | Global READ-Only (Audit / Oversight) | Relationship-Only (Eligible appointment or authored record) | Forbidden (403) |
| EMR Report Creation (`/medical/add/<appointment_id>`) | Forbidden (403) | Assigned Doctor Only (Terminal appointments excluded) | Forbidden (403) |
| EMR Report Edit (`/medical/edit/<record_id>`) | Forbidden (403) | Authoring Doctor Only | Forbidden (403) |
| EMR Report Deletion (`/medical/delete/<record_id>`) | **Permanently Forbidden (403)** | **Permanently Forbidden (403)** | **Permanently Forbidden (403)** |

---

## 4. Technology Stack

- **Backend Framework:** Python 3.10+, Flask 3.1, Werkzeug
- **Security & Integrity:** Flask-WTF (CSRF tokens on all POST requests), Flask-Limiter (Rate limiting)
- **Database & Engine:** MySQL 8.0 (InnoDB storage engine, foreign key constraints)
- **Database Connector:** `mysql-connector-python` using parameterized queries exclusively
- **Frontend & Styling:** Jinja2 dynamic templates, HTML5, CSS3, Bootstrap 5, Bootstrap Icons
- **Production Entrypoint:** WSGI (`wsgi.py`) with Gunicorn support and configurable ProxyFix
- **Testing Suite:** Python `unittest` suite (48 automated regression, security invariant, and real MySQL concurrency tests)

---

## 5. Security Architecture & Hardening

### Authentication & Account Lifecycle
- **Decommissioned Public Registration:** Public self-registration is eliminated; `/register` returns HTTP 404.
- **Fail-Closed CLI Bootstrap:** Initial administrator account is provisioned via `flask create-admin`, enforcing non-empty passwords and unique emails.
- **Password Protection:** Cryptographic hashing via Werkzeug security primitives (Scrypt / PBKDF2) with per-user salt generation.
- **Server-Side Session Revocation:** Every authenticated request queries the database via `@app.before_request` to verify user existence and role consistency. Demoted or deleted staff lose session access immediately (`session.clear()`).

### Relationship-Based Clinical Authorization
- **Doctor-Patient Access Policy:** Doctors see only patients where an appointment with status `zakazano` or `zavrseno` exists, or where the doctor authored an existing medical report. Cancelled appointments (`otkazano`) never establish access.
- **Parameter Tampering Prevention (IDOR):** In `/medical/add/<appointment_id>`, the patient ID is derived directly from the verified database appointment, ignoring client-supplied form values.
- **Strict Role Assignment:** Reassigning appointments requires validating that the target user ID holds the database role `doktor`.

### Medical Record Retention & Cascade Protection
- **Permanent Hard-Delete Elimination:** No route executes `DELETE FROM medical_records`. All deletion endpoints return HTTP 403, and deletion buttons are removed from the UI.
- **Cascade Deletion Guards:** Because foreign keys use `ON DELETE CASCADE` at the schema level, application-level transactions with row-level locks (`SELECT ... FOR UPDATE`) block the deletion of any doctor or patient who has historical appointments or medical records.
- **Terminal Appointment State:** Cancelled appointments cannot be changed back to scheduled or completed status. Completed appointments represent permanent clinical events and cannot be reassigned.

### HTTP Safety, Proxy & Logging Privacy
- **POST-Only State Changes:** All destructive operations and logout require HTTP POST; GET requests return HTTP 405 Method Not Allowed.
- **Strict CSRF Enforcement:** CSRF protection is enabled globally via `Flask-WTF`. Missing or invalid tokens return HTTP 400.
- **Untrusted Reverse Proxy by Default:** `ProxyFix` trusted hops defaults to `0`. `X-Forwarded-For` is ignored unless explicitly configured via `TRUSTED_PROXIES`.
- **Privacy-Safe Security Logs:** Diagnoses, therapies, session cookies, user passwords, emails, and full national IDs (JMBG) are completely excluded from server log entries.

---

## 6. Database Architecture

The relational schema comprises 5 normalized tables in MySQL:

```text
departments (id, naziv, opis)
     │
     └──< users (id, ime, email, password, role, department_id)
            │
            └──< appointments (id, patient_id, doctor_id, datum, status)
            │         │
patients ────┴────────┼───< medical_records (id, patient_id, doctor_id, dijagnoza, terapija, datum)
(id, ime, prezime, jmbg, telefon)
```

- `departments`: Specialty units (e.g., General Practice, Pediatrics).
- `users`: Clinical staff with role identifiers (`admin`, `doktor`, `sestra`).
- `patients`: Patient demographic directory with unique `jmbg` constraint.
- `appointments`: Scheduled consultations with status transitions (`zakazano`, `zavrseno`, `otkazano`).
- `medical_records`: Immutable longitudinal diagnostic entries and prescriptions.

---

## 7. Installation & Local Setup

### 1. Prerequisites
- Python 3.10+
- MySQL 8.0+

### 2. Environment Setup
```bash
git clone https://github.com/DimitrijeJovic/flask-medical-management-system.git
cd flask-medical-management-system

python -m venv .venv
# Linux/macOS:
source .venv/bin/activate
# Windows:
.\.venv\Scripts\activate

pip install -r requirements.txt
```

### 3. Database Initialization
Create the database and apply the initial schema:
```bash
mysql -u root -p -e "CREATE DATABASE dom_zdravlja_v1 CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;"
mysql -u root -p dom_zdravlja_v1 < schema.sql
```

### 4. Configuration
Copy the sample environment file:
```bash
cp .env.example .env
```
Generate a cryptographically strong secret key:
```bash
python -c "import secrets; print(secrets.token_urlsafe(32))"
```
Configure your `.env` file:
```ini
SECRET_KEY=your_generated_secret_key_here
FLASK_DEBUG=0
PORT=5000

DB_HOST=127.0.0.1
DB_PORT=3306
DB_NAME=dom_zdravlja_v1
DB_USER=your_db_username
DB_PASSWORD=your_db_password

TRUSTED_PROXIES=0
RATELIMIT_STORAGE_URI=memory://
```

### 5. Create Administrator Account
Run the interactive setup command:
```bash
flask create-admin
```
Provide the administrator's name, email, and password.

---

## 8. Running the Application

### Development Mode
```bash
python app.py
```
Open `http://127.0.0.1:5000` in your browser.

### Production WSGI Mode
Run using a WSGI server (e.g., Gunicorn on Linux):
```bash
gunicorn wsgi:app --workers 4 --bind 127.0.0.1:5000
```
*Note: `wsgi.py` performs immediate startup validation, terminating execution if `SECRET_KEY` is missing, blank, or set to an insecure default.*

---

## 9. Running Tests

Run the complete automated test discovery (all 48 tests):
```bash
python -m unittest discover -s tests -p "test_*.py"
```

### Test Suites:

1. **Unit & Security Regression Suite (`tests/test_app.py` — 38 Tests):**
   ```bash
   python -m unittest tests.test_app
   ```
   - Account creation & public registration decommissioning.
   - Role-based access control for Admin, Doctor, and Nurse.
   - EMR relationship-based access control and patient directory scoping.
   - Appointment ownership validation and terminal cancellation enforcement.
   - Hard delete prevention across all roles and cascade deletion guards.
   - Database session revalidation and demotion/deletion revocation.
   - Row-locking (`FOR UPDATE`) in appointment mutations.
   - CSRF validation, WSGI startup secrets, and logging privacy.

2. **Real MySQL Integration & Concurrency Suite (`tests/test_mysql_integration.py` — 10 Tests):**
   ```bash
   python -m unittest tests.test_mysql_integration
   ```
   - Doctor ownership validation on appointments (403 on unauthorized mutation).
   - Cancelled appointment terminal status (reopening blocked in database).
   - Completed appointment immutability (reassignment blocked).
   - Unauthorized EMR creation rejection and atomic commit validation.
   - Transaction rollback fidelity (zero residual rows on simulated failure).
   - Multi-connection row locking (`SELECT ... FOR UPDATE` verified with real InnoDB connection blocking).
   - Race condition serialization (concurrent attempts cleanly serialized; exactly 1 record created).
   - Real ReBAC `EXISTS` query execution against live MySQL database rows.
   - Parent-row deletion safeguards (doctors and patients with clinical records protected).

---

## 10. Known Limitations & Production Considerations

1. **In-Memory Rate Limiting:** Flask-Limiter uses `memory://` by default. For multi-process or clustered production deployments, set `RATELIMIT_STORAGE_URI=redis://localhost:6379/0` to enforce rate limits across workers.
2. **Database Concurrency Isolation:** Multi-connection row locking (`SELECT ... FOR UPDATE`) and race condition serialization have been positively verified against local MySQL 8.0 Community Server (InnoDB). Production environments should ensure InnoDB default `REPEATABLE READ` or `SERIALIZABLE` isolation.
3. **Foreign Key DDL vs Application Guard:** The underlying `schema.sql` retains `ON DELETE CASCADE` on historical foreign keys. While application routes strictly prevent cascade triggers by blocking doctor and patient deletions, direct manual SQL executions outside the application would cascade. A future migration to `ON DELETE RESTRICT` is recommended for enterprise setups.

---

## 11. Screenshots

*(Screenshots will be captured and added following staging deployment)*

| View | Description | Placeholder |
|---|---|---|
| **Admin Dashboard** | Clinic statistics, department overviews, staff management | `[ Screenshot: Admin Dashboard ]` |
| **Doctor Consultation Queue** | Assigned patient list, status controls, medical history link | `[ Screenshot: Doctor Queue ]` |
| **Electronic Medical Record** | Longitudinal consultation notes, diagnoses, and prescriptions | `[ Screenshot: Patient EMR ]` |
| **Appointment Scheduling** | Nurse booking portal with doctor and patient selection | `[ Screenshot: Scheduling Modal ]` |
