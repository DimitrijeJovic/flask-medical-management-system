# Security

This is an academic project that has never been deployed. This document records the security problems found in the first version of the application, how each was fixed, and what remains open. Every statement about current behaviour refers to code in `app.py`, `db.py`, or `wsgi.py`.

## Problems found in the first version (commit `1919ecd`)

| # | Problem | Effect |
|---|---|---|
| 1 | Public `/register` form let any visitor choose the `admin` role | Anyone could become an administrator |
| 2 | `/medical/<patient_id>` checked only that the caller was logged in | Any staff member could read any patient's medical history |
| 3 | Delete routes for users, patients, and medical records accepted GET | A link or image tag could delete records |
| 4 | No CSRF protection on any form | Cross-site requests could change data |
| 5 | Hard-coded secret key and database password; `debug=True` | Session forgery and remote debugger exposure if deployed |
| 6 | `ON DELETE CASCADE` in the schema with no application guard | Deleting a doctor or patient silently deleted medical history |

The first fix (commit `0e154bc`) was reviewed independently and rejected: administrators could still edit and delete medical records, a doctor could reopen a cancelled appointment to regain access, and every doctor could list all patients' national ID numbers. Those gaps were fixed in commit `5749007`.

## Current controls

| Area | Control | Location |
|---|---|---|
| Accounts | No public registration (`/register` returns 404). Staff accounts are created by an administrator; the first administrator by `flask create-admin`, which refuses to run if one exists | `app.py` routes `/users/add`, CLI `create-admin` |
| Passwords | Werkzeug `generate_password_hash` / `check_password_hash`; generic login error | `app.py` login and user creation |
| Sessions | On every request, the session's user ID and role are re-read from the database; a deleted or demoted user is logged out | `validate_runtime_security` (`@app.before_request`) |
| Role checks | `login_required` and `role_required` decorators; 403 on wrong role | `app.py` |
| Medical records | Doctors read a patient's records only with a scheduled or completed appointment, or a record they wrote. Cancelled appointments grant nothing. Administrators have read-only access. Nurses have none. No role can delete a record | `check_doctor_patient_relationship`, `/medical/*` routes |
| Record creation | The patient is taken from the appointment in the database, not from the form; only the assigned doctor, never on a cancelled appointment | `/medical/add/<appointment_id>` |
| Appointments | A doctor edits only their own appointments, cannot reassign them, and cannot reopen a cancelled one. Assigned users must have the role `doktor` | `/appointments/add`, `/appointments/edit/<id>` |
| Patient directory | Doctors see only related patients, without national ID numbers | `/patients`, `templates/patients.html` |
| Deletion guards | Deleting a doctor or patient with appointments or records is refused inside a transaction that locks the rows (`SELECT ... FOR UPDATE`) | user and patient delete routes |
| HTTP | Deletes and logout are POST-only; CSRF tokens on every form (Flask-WTF) | `app.py`, templates |
| Login throttling | 5 login POSTs per minute per client address (Flask-Limiter) | `@limiter.limit` on `/login` |
| Configuration | `SECRET_KEY` from the environment; requests fail if it is missing or a known default (outside test mode); `wsgi.py` refuses to start without it; debug off by default; `ProxyFix` only when `TRUSTED_PROXIES` is set | `app.py`, `wsgi.py`, `db.py` |
| Logging | Security events are logged without emails, diagnoses, or national ID numbers | `security_logger` calls |

## Remaining risks

| Risk | Note |
|---|---|
| Rate limiting is per process (`memory://`) | Several workers multiply the limit; use `RATELIMIT_STORAGE_URI` with Redis in a multi-process deployment |
| Schema still declares `ON DELETE CASCADE` | The application blocks cascading deletes, but SQL run outside the application would still cascade. A migration to `ON DELETE RESTRICT` would close this |
| The ownership re-check inside the appointment-edit transaction has no dedicated test | The earlier ownership check in the same route is tested; see `TESTING.md` |
| Early commits contain a development secret key and database password | Neither is used by the current code, which reads both from the environment and refuses the old key. The application was never deployed, so no server ever used the old key. The old password should be changed on any local MySQL account that may still use it |
