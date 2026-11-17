# Portfolio Project Summary: Healthcare Management System (Dom Zdravlja)

## 1. Project Overview
The **Healthcare Management System** is a secure outpatient clinic web application built with **Python, Flask, MySQL, and Bootstrap 5**. It manages clinical scheduling, staff roles, patient directories, and longitudinal electronic medical records (EMR) for a primary healthcare institution.

The core engineering focus was transforming an early full-stack prototype into an enterprise-grade, defensible application implementing **Zero-Trust authorization**, **immutable clinical history retention**, **database-backed session revocation**, and **safe concurrency safeguards**.

---

## 2. Technical Stack
- **Backend:** Python 3.10+, Flask 3.1, Werkzeug
- **Database:** MySQL 8.0 (InnoDB, foreign keys, row-level locking)
- **Database Access:** `mysql-connector-python` with parameterized SQL
- **Security:** Flask-WTF (CSRF tokens), Flask-Limiter (Rate limiting), Scrypt password hashing
- **Frontend:** Jinja2 server-rendered templates, Bootstrap 5, Bootstrap Icons
- **Production Server:** WSGI (`wsgi.py`) with Gunicorn support and ProxyFix reverse proxy handling
- **Testing:** Python `unittest` regression suite with mock isolation and mutation probes

---

## 3. Core Features
- **Role-Based Access Control (RBAC):** Distinct operational interfaces for **Administrator**, **Doctor (`doktor`)**, and **Nurse (`sestra`)**.
- **Relationship-Based Access Control (ReBAC):** Doctors access patient records only when a valid clinical relationship exists (scheduled/completed appointment or authored clinical record).
- **Clinical History Immutability:** Medical diagnoses and prescriptions cannot be permanently deleted by any role, preserving legal medical audit trails.
- **Terminal Consultation Auditing:** Cancelled appointments are permanently archived; completed appointments cannot be reassigned to alter historical authorship.
- **Scoped Patient Directory:** Doctor directory searches are bounded to legitimate patient relationships, omitting national ID (JMBG) data.

---

## 4. Key Engineering & Security Decisions

| Decision | Rationale | Engineering Trade-off |
|---|---|---|
| **Zero-Trust Application Cascade Guards** | The underlying relational schema specifies `ON DELETE CASCADE`. Rather than executing a high-risk schema migration without a live DB, application-level transaction checks (`SELECT ... FOR UPDATE` + dependent record counts) block deletion of doctors or patients who have historical records. | Preserved 100% schema backward compatibility while eliminating accidental clinical history loss through application workflows. |
| **Real-Time Session Validation** | Authenticated sessions verify user existence and role against the database on every request (`@app.before_request`). | Prevents privilege persistence when staff accounts are deleted or demoted, failing closed upon any database irregularity. |
| **Fail-Closed WSGI Startup** | In production, `wsgi.py` validates `SECRET_KEY` and database credentials before the WSGI application serves traffic. | Eliminates insecure default secrets and hardcoded credentials in production environments while keeping unit test module imports seamless. |
| **Untrusted Reverse Proxy Default** | `ProxyFix` trusted hops default to `0`. `X-Forwarded-For` headers are discarded unless an administrator explicitly configures `TRUSTED_PROXIES`. | Prevents client IP spoofing in security logs and rate-limiter bypasses in non-proxied environments. |

---

## 5. Testing Strategy & Verifiable Results
- **Automated Regression Suite:** **38 / 38 unit and route security tests passing (0.53s execution time)**.
  - Verification includes: public registration removal (404), RBAC route boundaries (403), hard delete prohibition (403/405), relationship scoping, terminal appointment status enforcement, session revocation on demotion/deletion, row locking in mutations, and CSRF enforcement.
- **Mutation Testing:** 5 deliberate security mutations (M1–M7) were executed against the test suite (e.g., adding `otkazano` to allowed statuses, disabling appointment ownership checks, disabling session validation, allowing non-doctor assignments, logging user emails). Every single mutation was successfully detected and failed the suite.
- **Integration Boundary Note:** Automated tests currently run with mock isolation. Real multi-connection MySQL integration tests were marked **NOT RUN** because the local database service was stopped and external infrastructure creation was not authorized.

---

## 6. Known Limitations & Roadmap
- **Rate Limiting Backend:** Currently uses process-local memory. Multi-worker production deployments should configure Redis (`RATELIMIT_STORAGE_URI=redis://...`).
- **Schema DDL Constraints:** Foreign keys retain `ON DELETE CASCADE` in `schema.sql`. A formal production migration should alter constraints to `ON DELETE RESTRICT`.
- **Soft Deletion / Archival:** Future iterations could introduce audit-logged soft-delete flags (`is_active`, `archived_at`) rather than hard foreign-key blocks.
