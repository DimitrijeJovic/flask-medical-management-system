# Architecture

## Structure

| Part | Responsibility |
|---|---|
| `app.py` | Flask application: configuration, security checks run before each request, role decorators, all routes, the `create-admin` command |
| `db.py` | Opens MySQL connections from environment variables; refuses missing credentials outside test mode |
| `wsgi.py` | Production entry point; refuses to start without a valid `SECRET_KEY` |
| `schema.sql` | Five tables: `departments`, `users`, `patients`, `appointments`, `medical_records` |
| `templates/` | Jinja2 pages rendered on the server (Bootstrap 5) |
| `tests/` | Unit suite (mocked database) and MySQL integration suite |

SQL is written by hand with parameterised queries through `mysql-connector-python`; there is no ORM.

## Request flow

1. `validate_runtime_security` runs first. It checks the secret key and, for logged-in users, re-reads their role from the database.
2. `login_required` or `role_required` decides whether the role may use the route.
3. The route checks the user's relationship to the data it touches (appointment ownership, doctor-patient relationship, record authorship).
4. Changes that must be consistent run in a transaction that locks the affected rows.

## Design decisions

| Decision | Reason | Trade-off |
|---|---|---|
| Block cascading deletes in the application instead of changing the schema | Keeps `schema.sql` unchanged; the application refuses to delete doctors or patients with history | SQL run outside the application can still cascade |
| Re-check the session against the database on every request | A deleted or demoted user loses access at once | One extra query per request |
| Medical records cannot be deleted through the application | Clinical history is kept | Mistaken entries must be corrected by editing |
| Cancelled appointments are final | Prevents regaining record access by reopening an appointment | A wrongly cancelled appointment must be booked again |
| `ProxyFix` only when `TRUSTED_PROXIES` is set | Clients cannot spoof their address when no proxy is present | Must be configured explicitly behind a proxy |
| Rate limits stored in memory by default | No extra service needed for local use | Not shared between processes; use Redis in production |
