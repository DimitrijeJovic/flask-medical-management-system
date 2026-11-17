# CV Project Entry: Healthcare Management System (Dom Zdravlja)

### Option A: Standard Full-Stack / Backend Developer Format

**Healthcare Management System (Dom Zdravlja)** | *Python, Flask, MySQL, Bootstrap 5, Werkzeug, Flask-WTF*  
*GitHub: `https://github.com/DimitrijeJovic/flask-medical-management-system`*

A role-based outpatient healthcare web application designed to manage clinical queues, appointment scheduling, and electronic medical records across administrative, medical, and nursing roles.

- Designed relational database architecture (5 normalized tables, foreign keys) and developed core application logic for patient intake, appointment scheduling, and clinical reporting using Flask and Jinja2 templates.
- Coordinated an AI-assisted security remediation to harden the application against OWASP Top 10 vulnerabilities, replacing open registration with a fail-closed CLI bootstrap and enforcing parameterized SQL queries.
- Implemented relationship-based access control (ReBAC) and parameter-tampering safeguards, restricting medical record reads and updates strictly to authoring doctors with active patient appointments.
- Architected database-backed session revocation and application-level cascade deletion guards (`SELECT ... FOR UPDATE`), preventing clinical history destruction without altering legacy database constraints.
- Built a 38-test automated regression suite with mock isolation and mutation probes, verifying RBAC boundaries, terminal appointment transitions, CSRF protection, and privacy-safe logging.

---

### Option B: QA Automation / Application Security Emphasis

**Flask Healthcare Management System — Security Hardening & QA Automation** | *Python, Flask, MySQL, Unittest, OWASP*  
*GitHub: `https://github.com/DimitrijeJovic/flask-medical-management-system`*

Full-stack medical clinic management system refactored and audited for strict access control, clinical history immutability, and relational integrity.

- Defined security requirements and verification criteria for multi-role outpatient workflows (Admin, Doctor, Nurse), eliminating privilege escalation vectors and unauthenticated administrative access.
- Coordinated remediation of authorization vulnerabilities (IDOR, open registration, cascade data loss), preventing unauthorized medical record editing and permanent diagnostic deletion.
- Developed an automated regression test suite of 38 unit and security tests in Python `unittest`, achieving deterministic test execution (<0.6s) across boundary conditions, row-level locking, and session invalidation.
- Conducted mutation testing across five deliberate security faults (e.g., appointment status bypasses, disabled ownership checks, session leakages), proving test suite efficacy and defect detection.
- Hardened production configuration with fail-closed WSGI secret validation, sanitized diagnostic logging, and disabled untrusted reverse-proxy header assumptions by default.

---

### Option C: Short One-Paragraph Portfolio Summary

**Healthcare Management System (Python / Flask / MySQL / Bootstrap 5):**  
Developed a full-stack clinical management web application with role-based and relationship-based access control (Admin, Doctor, Nurse). Spearheaded comprehensive security remediation and QA automation: eliminated public registration, enforced clinical history immutability, implemented real-time database session revocation, protected cascading foreign keys via application-level row locks (`SELECT ... FOR UPDATE`), and established a 38-test automated regression suite verified against mutation probes.  
*Repo: `https://github.com/DimitrijeJovic/flask-medical-management-system`*
