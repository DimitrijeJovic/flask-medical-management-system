# Healthcare Management System (Dom Zdravlja)

A role-based healthcare and clinic management web application built with **Python**, **Flask**, **MySQL**, and **Bootstrap 5**.

The system streamlines clinic workflows, patient registration, appointment scheduling, and electronic medical record (EMR) documentation across three distinct medical roles: **Administrator**, **Doctor**, and **Nurse**.

---

## 1. Core Features & Role-Based Access Control (RBAC)

The application enforces strict role segregation across authenticated session routes:

### 👨‍⚕️ Doctor (`doktor`)
- Dedicated physician dashboard displaying scheduled patient queues.
- Review patient appointment lists and historical visits.
- Author, update, and manage electronic medical records (EMR) with diagnoses and prescribed therapies.
- Mark appointment statuses as completed (`zavrseno`).

### 👩‍⚕️ Nurse (`sestra`)
- Clinical reception dashboard for outpatient intake.
- Patient directory management (register new patients, update records, validate national identity numbers / JMBG).
- Appointment scheduling and scheduling conflict management.
- Update appointment statuses (scheduled, completed, cancelled).

### 🛠️ Administrator (`admin`)
- Complete user lifecycle administration (create, update, delete clinical staff accounts).
- Department assignment (assign doctors to specialized clinical departments).
- System-wide audit overview of patient intake, appointment volumes, and medical records.

---

## 2. Technology Stack

| Layer | Technology | Purpose |
| :--- | :--- | :--- |
| **Backend Framework** | Python 3, Flask 3.1 | Core application routing, request handling, and session management |
| **Authentication & Security** | Werkzeug Security | Password hashing with secure cryptographic salt generation |
| **Database** | MySQL 8.0 (InnoDB) | Relational persistence, foreign key referential integrity, and cascading rules |
| **Database Connector** | `mysql-connector-python` | Direct parameterized SQL query execution |
| **Templating & UI** | Jinja2, HTML5, CSS3, Bootstrap 5 | Dynamic server-side rendering with responsive clinical UI layouts |

---

## 3. Database Architecture

The schema consists of **5 relational tables** modeled for transactional consistency:

```
+----------------+          +----------------+
|  departments   | 1      * |     users      |
|----------------|<---------|----------------|
| id (PK)        |          | id (PK)        |
| naziv, opis    |          | ime, email     |
+----------------+          | password, role |
                            | department_id  |
                            +----------------+
                                    | 1
                                    |
                                    | *
+----------------+          +----------------+          +-------------------+
|    patients    | 1      * |  appointments  | 1      * |  medical_records  |
|----------------|<---------|----------------|<---------|-------------------|
| id (PK)        |          | id (PK)        |          | id (PK)           |
| ime, prezime   |          | patient_id     |          | patient_id        |
| jmbg (UNIQUE)  |          | doctor_id      |          | doctor_id         |
| telefon        |          | datum, status  |          | dijagnoza         |
+----------------+          +----------------+          | terapija, datum   |
                                                        +-------------------+
```

- **`departments`**: Clinical departments and specialties.
- **`users`**: Staff accounts with role-based attributes (`admin`, `doktor`, `sestra`).
- **`patients`**: Patient personal profiles with unique national identification numbers (`jmbg`).
- **`appointments`**: Scheduled clinical consultations linking patients to doctors with datetime stamps and lifecycle statuses (`zakazano`, `zavrseno`, `otkazano`).
- **`medical_records`**: Diagnostic findings, historical clinical evaluations, and prescribed treatments.

---

## 4. Application Routes Overview

The application exposes **20 structured endpoints**:

- **Authentication:** `/`, `/login`, `/register`, `/logout`
- **Role Dashboards:** `/admin`, `/doktor`, `/sestra`
- **Staff Administration:** `/users`, `/users/delete/<id>`
- **Patient Intake:** `/patients`, `/patients/add`, `/patients/edit/<id>`, `/patients/delete/<id>`
- **Appointment Scheduling:** `/appointments`, `/appointments/add`, `/appointments/edit/<id>`
- **Medical Documentation:** `/medical/<patient_id>`, `/medical/add/<appointment_id>`, `/medical/edit/<id>`, `/medical/delete/<id>`

---

## 5. Local Setup & Installation

### Prerequisites
- Python 3.10+
- MySQL Server 8.0+
- Git

### 1. Clone the Repository
```bash
git clone https://github.com/DimitrijeJovic/flask-medical-management-system.git
cd flask-medical-management-system
```

### 2. Configure Virtual Environment & Dependencies
```bash
python -m venv venv

# Linux / macOS:
source venv/bin/activate

# Windows:
.\venv\Scripts\activate

pip install -r requirements.txt
```

### 3. Initialize Database
Import the relational schema into your local MySQL server:
```bash
mysql -u root -p < schema.sql
```

### 4. Configure Environment Variables (Optional)
The application reads configuration from environment variables with safe development defaults:
```bash
# Optional overrides:
export DB_HOST="127.0.0.1"
export DB_PORT="3306"
export DB_USER="root"
export DB_PASSWORD="your_password"
export DB_NAME="dom_zdravlja_v1"
export SECRET_KEY="your_secure_random_key"
```

### 5. Run the Application
```bash
python app.py
```
Open [http://127.0.0.1:5000](http://127.0.0.1:5000) in your web browser.

---

## 6. License & Attribution

Developed as an academic software engineering project demonstrating full-stack web architecture, relational schema normalization, and role-based access control with Python and Flask.
