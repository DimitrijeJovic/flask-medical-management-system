# Healthcare Management System (Dom Zdravlja)

A secure, role-based healthcare and outpatient clinic management web application built with Python, Flask, MySQL, and Bootstrap 5.

This project was my first software development project, created to explore full-stack web architecture, server-rendered dynamic templates, relational database modeling, role-based access control, and robust application security hardening.

---

## Overview & Scope

The application manages day-to-day administrative and outpatient workflows in a medical center. It provides dedicated views and role-restricted actions for three types of clinic staff:

- **Administrator:** System oversight, staff directory management, and user lifecycle administration.
- **Doctor (`doktor`):** Outpatient queue review, electronic medical record (EMR) documentation, diagnosis and therapy entry, and consultation status updates.
- **Nurse (`sestra`):** Patient intake registration, identity validation, appointment scheduling, and consultation status tracking.

---

## Security Architecture & Hardening

The application incorporates enterprise-grade security controls aligned with OWASP Top 10 guidelines:

### Authentication & Account Lifecycle
- **Decommissioned Public Registration:** Anonymous registration endpoints are completely disabled. Only authenticated administrators can create staff accounts at `/users/add`.
- **Fail-Closed Bootstrap:** Initial administrator creation is securely performed via an interactive, fail-closed CLI command (`flask create-admin`) with hidden password input.
- **Password Security:** Scrypt password hashing via Werkzeug security primitives with unique salts.
- **Flask View Decorators:** Standard `@wraps` view decorators (`@login_required`, `@role_required`) protecting all internal endpoints.

### Granular Authorization & Medical Record Integrity
- **Role-Based Access Control:** Nurses and unauthenticated users receive HTTP 403 when requesting clinical records.
- **Relationship-Based EMR Access:** Doctors may access a patient's medical history only if an active/completed appointment exists or if the doctor authored historical clinical records for that patient. Cancelled appointments (`otkazano`) explicitly do not grant access.
- **Creation Integrity:** Diagnostic reports can only be added by the assigned doctor for their own appointments. Patient IDs are derived strictly from the database appointment record, preventing IDOR/parameter tampering.

### Database Integrity & Cascade Protection
- **Application-Level Deletion Guards:** Because database foreign keys use `ON DELETE CASCADE`, application-level transaction checks block deleting doctors or patients who have associated appointments or clinical records, preserving medical history.
- **Concurrency & Row Locking:** Deletion routines utilize explicit transactions and parent-row locking (`SELECT ... FOR UPDATE`) to eliminate race conditions with concurrent appointment bookings.

### HTTP Method Safety & CSRF Protection
- **POST-Only Destructive Actions:** All deletion operations and session logouts require HTTP POST; direct GET requests return HTTP 405 Method Not Allowed.
- **Comprehensive CSRF Protection:** All state-changing forms across all templates are protected by `Flask-WTF` CSRF tokens, with dedicated error handling for invalid/expired tokens.
- **Login Rate Limiting:** Brute-force credential attacks on `/login` are throttled via `Flask-Limiter`.

### Production Configuration & WSGI Hardening
- **Validated WSGI Startup:** Production entry point `wsgi.py` strictly verifies that a non-empty, cryptographically secure `SECRET_KEY` is provided before the WSGI server accepts requests.
- **Exception Sanitization:** Raw database exceptions are masked in user-facing flash notifications and recorded in server diagnostic logs.

---

## Technology Stack

- **Backend:** Python 3, Flask 3.1, Werkzeug
- **Security:** Flask-WTF (CSRF), Flask-Limiter (Rate Limiting)
- **Production Server:** WSGI (`wsgi.py`) with Gunicorn support and ProxyFix reverse proxy handling
- **Database:** MySQL 8.0 (InnoDB engine, foreign key constraints)
- **Database Access:** `mysql-connector-python` with parameterized prepared statements
- **Frontend:** Jinja2 server-rendered templates, HTML5, CSS3, Bootstrap 5, Bootstrap Icons
- **Testing:** Python `unittest` regression test suite with mock isolation and CLI test runner

---

## Application Structure

```text
flask-medical-management-system/
├── app.py              # Application routes, authorization decorators, and business logic
├── wsgi.py             # Production WSGI entry point with startup validation
├── db.py               # Database connection helper with environment variable loading
├── schema.sql          # Relational schema DDL (5 tables)
├── requirements.txt    # Pinned Python package dependencies
├── .env.example        # Template for required environment variables
├── .gitignore          # Git exclusion rules for virtual environments, secrets, and caches
├── static/
│   └── css/
│       └── style.css   # Custom clinic UI styles, typography, and dark-mode themes
├── templates/          # Jinja2 templates for dashboards, CRUD views, and auth
└── tests/
    └── test_app.py     # Automated security, RBAC, and regression test suite
```

---

## Database Architecture

The schema consists of 5 normalized tables in MySQL 8.0:

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

- `departments`: Clinical specialties and service units.
- `users`: Clinical personnel with role attributes (`admin`, `doktor`, `sestra`).
- `patients`: Patient demographic directory with unique `jmbg` constraint.
- `appointments`: Scheduled clinical visits with datetime timestamps and status states (`zakazano`, `zavrseno`, `otkazano`).
- `medical_records`: Longitudinal clinical consultation notes and prescriptions.

---

## Installation & Setup

### 1. Prerequisites
- Python 3.10+
- MySQL 8.0+

### 2. Environment Setup
Clone the repository and set up a virtual environment:
```bash
git clone https://github.com/DimitrijeJovic/flask-medical-management-system.git
cd flask-medical-management-system

python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

### 3. Database Initialization
Create the database and apply the schema:
```bash
mysql -u root -p -e "CREATE DATABASE dom_zdravlja_v1 CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;"
mysql -u root -p dom_zdravlja_v1 < schema.sql
```

### 4. Configuration
Copy the example environment configuration and generate a secure secret key:
```bash
cp .env.example .env
```
Generate a secret key:
```bash
python -c "import secrets; print(secrets.token_urlsafe(32))"
```
Configure your `.env` with the generated `SECRET_KEY`, database credentials (`DB_USER`, `DB_PASSWORD`), and port.

### 5. Create Initial Administrator
Bootstrap the initial administrator account:
```bash
flask create-admin
```
Follow the interactive prompts to enter the admin name, email, and password.

---

## Running the Application

### Local Development
```bash
python app.py
```
Access the application at `http://127.0.0.1:5000`.

### Production Deployment (WSGI)
Run the application using a production WSGI server behind a reverse proxy (e.g., Nginx):
```bash
gunicorn wsgi:app --workers 4 --bind 127.0.0.1:5000
```

---

## Running Tests

Execute the automated test suite:
```bash
python -m unittest tests.test_app
```
The test suite covers public registration decommissioning, RBAC authorization, IDOR boundary protection, destructive HTTP method enforcement, cascade deletion guards, and CSRF error handling.
