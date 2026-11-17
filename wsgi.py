# wsgi.py — Production WSGI Entrypoint
import os

# 1. True Startup Validation: Validate environment BEFORE importing application module
raw_secret = os.environ.get("SECRET_KEY")
insecure_defaults = ("sifra", "secret", "default", "changeme", "password")

if not raw_secret or raw_secret.strip() == "" or raw_secret.strip().lower() in insecure_defaults:
    raise RuntimeError(
        "FATAL WSGI STARTUP ERROR: The 'SECRET_KEY' environment variable is missing, "
        "empty, whitespace-only, or using an insecure default. WSGI application loading aborted."
    )

# 2. Import application strictly after environment is verified
from app import app as application

# Strict Isolation: Production WSGI cannot run with test bypasses
application.config["TESTING"] = False
application.secret_key = raw_secret

app = application

if __name__ == "__main__":
    application.run()
