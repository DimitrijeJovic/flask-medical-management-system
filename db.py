import os

try:
    import mysql.connector
except ImportError:
    mysql = None


def get_db_connection():
    if mysql is None:
        raise RuntimeError(
            "mysql-connector-python is not installed. "
            "Please install it with 'pip install -r requirements.txt'."
        )

    # In non-testing environments, database credentials must be explicitly provided via environment variables
    db_host = os.environ.get("DB_HOST", "127.0.0.1")
    db_port = int(os.environ.get("DB_PORT", "3306"))
    db_name = os.environ.get("DB_NAME", "dom_zdravlja_v1")

    db_user = os.environ.get("DB_USER")
    db_password = os.environ.get("DB_PASSWORD")

    is_testing = os.environ.get("FLASK_ENV") == "testing" or os.environ.get("TESTING") == "1"

    if not db_user:
        if is_testing:
            db_user = "test_user"
        else:
            raise RuntimeError("DATABASE CONFIGURATION ERROR: DB_USER environment variable is required.")

    if db_password is None:
        if is_testing:
            db_password = ""
        else:
            raise RuntimeError("DATABASE CONFIGURATION ERROR: DB_PASSWORD environment variable is required.")

    return mysql.connector.connect(
        host=db_host,
        user=db_user,
        password=db_password,
        database=db_name,
        port=db_port,
    )
