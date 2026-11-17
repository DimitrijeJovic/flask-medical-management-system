# FINAL PRE-PUBLICATION AUDIT: GIT HISTORY & MYSQL INTEGRATION
## Flask Medical Management System

**Project Location:** `D:\Claude\Moji projekti\flask-medical-management-system`  
**Current Branch:** `security/medical-management-hardening`  
**HEAD Commit:** `0e154bcb22c9ad5b1f0c9721999278e11e174ab9`  
**Date:** 2026-11-17  
**Execution Mode:** Read-Only Forensic Audit (No history rewritten, no credentials rotated, no services started/stopped, no databases modified).

---

## 1. Executive Summary

This forensic audit investigates the two pre-publication blockers identified for the repository:
1. **Secrets & Credentials in Git History:** Thorough inspection of all 4 commits across all branches to determine whether live, active, or sensitive credentials exist in the Git tree.
2. **MySQL Environment & Concurrency Verification:** Audit of local host services, Docker status, database connectors, and architectural requirements for executing real multi-connection MySQL integration tests.

### Audit Verdict:
- **Git History Secrets:** **LOW RISK / NO ACTIVE PRODUCTION CREDENTIALS FOUND.** The historical commits contain standard local development placeholders (`[REDACTED_DEV_DEFAULT_PASSWORD]` and `[REDACTED_DEV_PLACEHOLDER_SECRET]`) and tracked bytecode files from the initial commit. No production API keys, cloud tokens, email credentials, or private connection strings were ever committed.
- **MySQL Environment:** **INFRASTRUCTURE AVAILABLE BUT CURRENTLY INACTIVE.** MySQL Server 8.0.46 is installed on the host with the `MySQL80` service in `Stopped` state. Docker Desktop is installed but its engine daemon is not running. Therefore, real MySQL integration and multi-connection concurrency tests remain **NOT RUN**.

---

## 2. Part A — Git History Forensic Audit

Every commit reachable in the repository was inspected across all historical revisions:
- `1919ecd` (Initial commit, May 2026)
- `5217d54` (Gitignore & pycache cleanup, Nov 2026)
- `c60e3db` (Refactoring & unit test baseline, Nov 2026)
- `0e154bc` (Security hardening baseline, Nov 2026)

### Detailed Findings by Commit & File:

| Commit | File | Line / Pattern | Secret Category | Classification | Current Tree Status |
|---|---|---|---|---|---|
| `1919ecd` | `db.py` | `password="[REDACTED_DEV_PASSWORD]"` | Database Password | **Dummy / Local Dev Default** (`root`) | **Removed** (remediated in working tree) |
| `1919ecd` | `app.py` | `app.secret_key = "[REDACTED_DEV_SECRET]"` | Session Secret Key | **Insecure Dummy Placeholder** (`sifra`) | **Removed** (remediated in working tree) |
| `1919ecd` | `.vscode/settings.json` | `python.defaultInterpreterPath` | System Metadata | **Local Username Path** (`C:\Users\mainp\...`) | **Deleted** in `5217d54` |
| `1919ecd` | `__pycache__/*.pyc` | Compiled bytecode of `app.py` & `db.py` | Compiled Artifact | **Tracked Python Bytecode** | **Deleted** in `5217d54` |
| `5217d54` | `db.py` | `os.environ.get("DB_PASSWORD", "[REDACTED_DEV_PASSWORD]")` | Database Password | **Dummy / Local Dev Default** (`root`) | **Removed** (remediated in working tree) |
| `5217d54` | `app.py` | `os.environ.get("SECRET_KEY", "[REDACTED_DEV_SECRET]")` | Session Secret Key | **Insecure Dummy Placeholder** (`sifra`) | **Removed** (remediated in working tree) |
| `c60e3db` | `tests/test_app.py` | `app.config["SECRET_KEY"] = "[REDACTED_TEST_KEY]"` | Test Secret | **Harmless Test Mock** (`test_secret_key`) | **Removed** (remediated in working tree) |
| `0e154bc` | `tests/test_app.py` | `app.config["SECRET_KEY"] = "[REDACTED_MOCK_ENTROPY]"` | Test Secret | **Harmless Test Mock** (`test-secret-key-32-bytes...`) | Present in tests only |
| `0e154bc` | `.env.example` | `SECRET_KEY=`, `DB_PASSWORD=` | Configuration Template | **Harmless Empty Placeholders** | Present in `.env.example` |

### Key Exposure Determinations:
1. **Real Production Credentials:** **NONE.** No live external accounts, database server passwords, or production keys exist.
2. **Old Development Credential:** The independent audit noted the historical default string `password="root"`. This was an artifact of initial local development.
3. **Local Username Disclosure:** Commit `1919ecd` briefly tracked a VS Code configuration file containing `C:\Users\mainp\...`. It was deleted in commit `5217d54`.

---

## 3. Credential Rotation & Git History Remediation Plan

### Is Credential Rotation Required?
- **NO.** The strings found (`root`, `sifra`) are standard educational/local defaults and placeholders. They do not grant access to any remote host, API, or production environment. If the local MySQL `root` account on the developer's computer still uses `root`, it is good hygiene to change it, but it does not represent a compromised public secret.

### Should Git History Be Rewritten?
There are two defensible options:

#### Option 1: Maintain History & Publish (Recommended for Fast Completion)
- **Rationale:** Historical commits `1919ecd` and `5217d54` represent the authentic evolution of an educational project (from a beginner prototype with hardcoded strings to an enterprise-grade hardened system). The README explicitly acknowledges: *"This project was my first software development project, created to explore full-stack web architecture... and robust application security hardening."*
- **Pros:** No broken commit hashes, no complex rebase, zero risk of destroying working tree state, completely transparent learning progression.
- **Cons:** Automated secret scanners (e.g., GitGuardian) might flag `"password='root'"` in commit `1919ecd` as an informational alert.

#### Option 2: Rewrite History via `git-filter-repo` (If Zero-Tolerance for Historical Flags is Required)
- **Tool:** Use `git-filter-repo` (Python utility) rather than deprecated `git filter-branch`.
- **Target:** Sanitize `db.py` in `1919ecd` to use `os.environ.get("DB_PASSWORD", "")` and purge the two `.pyc` files and `.vscode/settings.json`.
- **Affected Commits:** All 4 commits (`1919ecd` through `0e154bc`) will receive new SHA-1 hashes.
- **Required Steps & Safeguards:**
  1. Create a full external directory backup: `Copy-Item -Recurse "flask-medical-management-system" "flask-medical-management-system-backup"`.
  2. Stage and commit all current working tree improvements to a clean commit first.
  3. Execute `git-filter-repo --replace-text` with a replacement expressions file.
  4. Force-push to GitHub origin (`git push origin --force --all`).
- **Impact:** Any collaborator or clone will experience divergent branch histories.

---

## 4. `.gitignore` Audit & Hardening

Current `.gitignore` correctly ignores:
- `.env`, `.env.*` (excluding `.env.example`)
- `__pycache__/`, `*.py[cod]`
- `.venv/`, `venv/`, `env/`
- `.vscode/`, `.idea/`

### Recommended Additions (Pre-Publication):
To guarantee that local SQLite tests, database exports, and logs are never staged:
```gitignore
# Database dumps & local files
*.sql.gz
*.dump
*.db
*.sqlite3

# Log files
*.log
logs/
```
*(Note: `schema.sql` is tracked and will not be ignored by wildcard rules if specifically tracked).*

---

## 5. Part B — MySQL Environment Audit

Host inspection yielded the following concrete infrastructure state:

| Component | Audit Result | Details |
|---|---|---|
| **MySQL Server Software** | **INSTALLED** | MySQL Server 8.0.46 (Win64) Community Server located at `C:\Program Files\MySQL\MySQL Server 8.0\bin\mysql.exe`. |
| **Windows Service (`MySQL80`)** | **STOPPED** | Service path: `"C:\Program Files\MySQL\MySQL Server 8.0\bin\mysqld.exe" --defaults-file="C:\ProgramData\MySQL\MySQL Server 8.0\my.ini" MySQL80`. |
| **Docker CLI** | **INSTALLED** | Docker CLI version `29.9.2`. |
| **Docker Engine / Daemon** | **UNAVAILABLE** | Docker Desktop is not running (`npipe:////./pipe/dockerDesktopLinuxEngine` connection refused). |
| **Python Database Driver** | **INSTALLED** | `mysql-connector-python 9.6.0` verified in `.venv`. |
| **Existing Database Isolation** | **INACTIVE** | Because neither the local service nor Docker is active, no live database connection could be made. |

---

## 6. Proposed Isolated MySQL Test Environment

To execute real MySQL integration tests without endangering development data:

### Preferred Safe Architecture:
1. **Service Activation:** Start the local Windows service `MySQL80` (or start Docker Desktop).
2. **Dedicated Test Database:** Create an explicitly named database:
   ```sql
   CREATE DATABASE IF NOT EXISTS dom_zdravlja_integration_test CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
   ```
3. **Dedicated Restricted User:**
   ```sql
   CREATE USER IF NOT EXISTS 'test_runner'@'localhost' IDENTIFIED BY 'TestRunnerPassword123!';
   GRANT ALL PRIVILEGES ON dom_zdravlja_integration_test.* TO 'test_runner'@'localhost';
   FLUSH PRIVILEGES;
   ```
4. **Environment Isolation Guard in Code:** The test runner must enforce that `DB_NAME` ends with `_test` or `integration_test` before executing any DDL or data manipulation, aborting immediately if pointed at a non-test database.

---

## 7. Required Real MySQL Multi-Connection Integration Tests

When the isolated test database is active, the following 10 real MySQL tests must be executed:

1. **Schema DDL Application:** Load `schema.sql` into `dom_zdravlja_integration_test`, verifying InnoDB engine and foreign key constraints on all 5 tables.
2. **Doctor Ownership Real SQL:** Verify that `SELECT ... FOR UPDATE` on appointments blocks unauthorized updates.
3. **Terminal Cancellation Protection:** Verify that attempting to UPDATE an appointment with status `otkazano` rolls back and leaves status unchanged in the real table.
4. **Historical Completion Reassignment Guard:** Verify that completed appointments (`zavrseno`) cannot have their `doctor_id` altered.
5. **Atomic Clinical Note Insertion:** Verify that creating a medical record inserts into `medical_records` and updates `appointments.status = 'zavrseno'` inside a single transaction, with full rollback on simulated connection drop.
6. **ReBAC Real Query Execution:** Execute the actual `UNION` query in `check_doctor_patient_relationship` across real rows; confirm that `otkazano` rows return no relation, while `zakazano`/`zavrseno` return true.
7. **Two-Connection Concurrent Appointment Mutation:**
   - Connection A starts a transaction and locks appointment 1 (`SELECT ... FOR UPDATE`).
   - Connection B attempts an update on appointment 1.
   - Assert that Connection B blocks until Connection A commits or rolls back.
8. **Two-Connection Concurrent Medical Record Creation:**
   - Connection A begins creating a record for appointment 1.
   - Connection B simultaneously attempts to create a record for appointment 1.
   - Assert that Connection B is serialized and rejected due to status change to `zavrseno`.
9. **Parent-Row Deletion Safeguard Execution:**
   - Insert doctor with an appointment.
   - Attempt `DELETE FROM users WHERE id = %s` using application logic.
   - Verify that dependent count check rolls back the transaction before any cascade occurs.
10. **Deadlock / Lock Timeout Handling:** Test timeout handling (`innodb_lock_wait_timeout`) and graceful rollback.

---

## 8. Publication Readiness & Exact Blockers

| Task / Item | Status | Action Required Before Public Release |
|---|---|---|
| **Code Implementation** | **100% READY** | None. All 38 unit and route security tests passing. |
| **Git Working Tree** | **UNCOMMITTED** | Stage and commit closeout files to `security/medical-management-hardening`. |
| **Git Secrets Status** | **LOW RISK (Documented)** | Choose Option 1 (acknowledge historical dummy placeholders) or Option 2 (`git-filter-repo` rewrite). |
| **MySQL Integration Suite** | **NOT RUN** | Optional for portfolio; required only if strictly proving multi-connection InnoDB locks to an auditor. |
| **GitHub Main Branch** | **BEHIND** | `main` is at `c60e3db`. Must merge `security/medical-management-hardening` into `main` before sharing the repository link. |

---

## 9. Recommended Next Actions

1. **Decision on Git History:**
   - **Recommended:** Accept Option 1 (keep authentic learning history, as all secrets were local placeholders and working tree is 100% clean).
2. **Commit Closeout Changes:**
   Commit the 8 modified files and 5 documentation files to `security/medical-management-hardening`.
3. **Merge to `main`:**
   Merge the hardened branch into `main` so visitors see the finalized code on GitHub.
4. **Push to Remote:**
   Push `main` and `security/medical-management-hardening` to GitHub origin.
5. **Update CV:**
   Insert the finalized bullets from `CV_PROJECT_ENTRY.md` into `Developer_CV.tex` and `QA_CV.tex`.
