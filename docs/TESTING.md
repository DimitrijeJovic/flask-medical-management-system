# Testing

The project has two `unittest` suites.

| Suite | File | Tests | Needs |
|---|---|---:|---|
| Unit and security regression | `tests/test_app.py` | 39 | Nothing; the database is mocked |
| MySQL integration | `tests/test_mysql_integration.py` | 10 | A MySQL 8 server (see below) |

## Running

```bash
python -m unittest tests.test_app                      # unit suite
python -m unittest tests.test_mysql_integration        # integration suite
python -m unittest discover -s tests -p "test_*.py"    # both
```

### MySQL for the integration suite

The integration suite uses, in this order:

1. a server already listening on `DB_HOST:DB_PORT` (default `127.0.0.1:3306`), connecting as `DB_USER` / `DB_PASSWORD` (default `root` with no password); or
2. a throwaway server it starts itself from the `mysqld` binary named by `MYSQLD_BIN`, or found on `PATH`. Its data directory is created in the system temp folder, and the suite shuts it down afterwards.

If neither is available, each of the 10 tests is reported as **skipped** (`OK (skipped=10)`), not as passed.

All work happens in the database named by `MYSQL_TEST_DB` (default `dom_zdravlja_integration_test`). Its tables are emptied before every test, so the suite refuses to run unless the name contains `test`. Never point it at a database that holds real data.

Example (Windows, throwaway server):

```powershell
$env:MYSQLD_BIN = "C:\Program Files\MySQL\MySQL Server 8.0\bin\mysqld.exe"
python -m unittest tests.test_mysql_integration
```

## What the unit suite covers

- Public registration removed; anonymous users redirected to login; logout is POST-only.
- Role restrictions for administrator, doctor, and nurse pages; staff creation; the `create-admin` command.
- Medical-record access: nurses refused, unrelated doctors refused, related doctors allowed; record creation only on one's own, non-cancelled appointment; the patient taken from the appointment, not the form.
- Administrators cannot edit records; no role can delete them.
- Doctors cannot reopen cancelled appointments or edit another doctor's appointment.
- Doctor patient directory: scoped, without national ID numbers, and not searchable by them.
- Session revocation after deletion or demotion; database errors during the check fail closed.
- Only users with the role `doktor` can be assigned to appointments.
- Deletion guards for doctors and patients with history; row locking and transactions on record creation.
- CSRF rejection, secret-key validation, database-credential validation, and email-free security logs.
- Login rate limiting: the sixth POST within a minute returns 429.

## What the integration suite covers

Run against a real MySQL 8 (InnoDB) database:

1. A doctor cannot edit another doctor's appointment (403).
2. A cancelled appointment cannot be reopened; its status stays `otkazano`.
3. A completed appointment cannot be reassigned to another doctor.
4. A doctor cannot create a record on an appointment that is not theirs (403).
5. Creating a record and completing the appointment happen in one transaction.
6. A failure inside that transaction leaves no partial rows.
7. `SELECT ... FOR UPDATE` on one connection blocks a second connection until commit.
8. Two concurrent record creations for the same appointment produce exactly one record.
9. The doctor-patient relationship query works against real rows.
10. Doctors and patients with clinical history cannot be deleted.

## Mutation check

To see whether the unit suite actually detects broken rules, single faults were introduced into a scratch copy of `app.py` and the unit suite was run against each (17 November 2026):

| Fault introduced | Result |
|---|---|
| Cancelled appointments grant record access | Detected |
| Ownership pre-check in appointment edit removed | Detected |
| Ownership re-check inside the appointment-edit transaction removed | **Not detected**: the earlier check in the same route still blocks the request, so this second check has no test of its own |
| Session no longer re-checked against the database | Detected |
| Non-doctor accepted as an appointment's doctor | Detected |
| Staff email written to the security log | Detected |
| Medical records deletable again | Detected |
| Login limit loosened from 5 to 50 per minute | Detected |

This was a one-off manual check, not an automated part of the suite.
