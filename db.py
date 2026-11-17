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

    # In non-testing environments, database credentials must be provided via environment variables
    db_host = os.environ.get("DB_HOST", "127.0.0.1")
    db_user = os.environ.get("DB_USER", "root")
    db_password = os.environ.get("DB_PASSWORD", "")
    db_name = os.environ.get("DB_NAME", "dom_zdravlja_v1")
    db_port = int(os.environ.get("DB_PORT", "3306"))

    return mysql.connector.connect(
        host=db_host,
        user=db_user,
        password=db_password,
        database=db_name,
        port=db_port,
    )
