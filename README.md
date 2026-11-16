# Healthcare Management System (Dom Zdravlja)

A role-based healthcare and outpatient clinic management web application built with Python, Flask, MySQL, and Bootstrap 5.

This project was my first software development project, created to explore full-stack web architecture, server-rendered dynamic templates, relational database modeling, and role-based access control.

---

## Overview & Scope

The application manages day-to-day administrative and outpatient workflows in a medical center. It provides dedicated views and role-restricted actions for three types of clinic staff:

- **Administrator:** System oversight, staff directory management, and user lifecycle administration.
- **Doctor (`doktor`):** Outpatient queue review, electronic medical record (EMR) documentation, diagnosis and therapy entry, and consultation status updates.
- **Nurse (`sestra`):** Patient intake registration, identity validation, appointment scheduling, and consultation status tracking.

---

## Implemented Functionality

### Authentication & Authorization
- Session-based authentication using HTTP-only signed cookies.
- Password hashing with salt generation via Werkzeug security primitives.
- Route-level access enforcement via role-checking decorators (`admin`, `doktor`, `sestra`).
- Automatic redirection of unauthenticated requests to the login view.

### Patient Directory & Intake
- Patient registration with required first name, last name, unique national identification number (JMBG), and contact telephone.
- JMBG format validation (13-digit numeric requirement) and duplicate entry handling.
- Paginated patient listing (8 records per page) with search filtering across first and last names.
- Role-scoped patient access: doctors only see patients with whom they have recorded consultations, while nurses and administrators see the clinic-wide register.

### Appointment Scheduling
- Appointment booking interface linking patients to available physicians with date and time selection.
- Lifecycle status tracking: Scheduled (`zakazano`), Completed (`zavrseno`), and Cancelled (`otkazano`).
- Appointment overview table displaying patient, assigned doctor, scheduled date/time, and status pills.

### Electronic Medical Records (EMR)
- Patient medical profile displaying historical visits, assigned physician, and department metadata.
- Clinical report documentation: doctors enter clinical diagnoses and prescribed therapies upon completing consultations.
- Record author verification: doctors can modify or remove their own clinical reports; administrators retain maintenance access.

---

## Technology Stack

- **Backend:** Python 3, Flask 3.1, Werkzeug
- **Database:** MySQL 8.0 (InnoDB engine, foreign key constraints with cascade rules)
- **Database Access:** `mysql-connector-python` with parameterized prepared statements
- **Frontend:** Jinja2 server-rendered templates, HTML5, CSS3, Bootstrap 5, Bootstrap Icons
- **Testing:** Python `unittest` suite with Flask test client and mock isolation

---

## Application Structure

```text
flask-medical-management-system/
├── app.py              # Application factory, route handlers, and authorization logic
├── db.py               # Database connection helper with environment variable fallback
├── schema.sql          # Relational schema DDL (5 tables)
├── requirements.txt    # Pinned Python package dependencies
├── .gitignore          # Git exclusion rules for virtualenvs, bytecode, and IDE configs
├── static/
│   └── css/
│       └── style.css   # Custom clinic UI styles, typography, and theme definitions
├── templates/          # Jinja2 templates for auth, dashboards, and CRUD views
└── tests/
    └── test_app.py     # Automated unit and integration test suite
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
- `appointments`: Scheduled clinical visits with datetime timestamps and status states.
- `medical_records`: Longitudinal clinical consultation notes and prescriptions.

---

## Installation & Setup

### Prerequisites
- Python 3.10+
- MySQL Server 8.0+
- Git

### 1. Clone the Repository
```bash
git clone https://github.com/DimitrijeJovic/flask-medical-management-system.git
cd flask-medical-management-system
```

### 2. Set Up Virtual Environment
```bash
python -m venv venv

# Linux / macOS:
source venv/bin/activate

# Windows:
.\venv\Scripts\activate

pip install -r requirements.txt
```

### 3. Initialize the Database
```bash
mysql -u root -p < schema.sql
```

### 4. Configuration
Configuration parameters can be supplied via environment variables or default to standard local values:

| Variable | Default Value | Description |
| :--- | :--- | :--- |
| `DB_HOST` | `127.0.0.1` | MySQL server host |
| `DB_PORT` | `3306` | MySQL server port |
| `DB_USER` | `root` | Database user |
| `DB_PASSWORD` | `root` | Database password |
| `DB_NAME` | `dom_zdravlja_v1` | Database name |
| `SECRET_KEY` | *(Development key)* | Flask session signing secret |

### 5. Run the Application
```bash
python app.py
```
Access the application at `http://127.0.0.1:5000`.

---

## Automated Testing

The repository includes an automated regression test suite validating authentication, role-based access control, input validation, and medical record author verification:

```bash
python -m unittest discover tests
```

Tests execute against Flask's test client and mock database layers, allowing execution without an active local MySQL service.

---

## Known Limitations & Development Context

As my first software engineering project, the application reflects early architectural decisions and provides opportunities for future refinement:

1. **Single-File Architecture:** All 20 route handlers currently reside in `app.py`. A future refactoring would modularize them into Flask Blueprints (e.g., `auth`, `patients`, `appointments`, `medical`).
2. **Raw SQL Operations:** Database interaction relies directly on `mysql-connector-python` queries. While parameterized to prevent SQL injection, an ORM such as SQLAlchemy would provide cleaner data modeling and migration tracking.
3. **Department CRUD:** While `departments` exists in the relational schema and is joined in queries, department management is currently handled directly in the database rather than through an administrative UI.
4. **CSRF Tokens:** Session protection relies on signed session cookies. Implementing explicit CSRF tokens (such as `Flask-WTF`) would provide defense-in-depth against cross-site request forgery.
