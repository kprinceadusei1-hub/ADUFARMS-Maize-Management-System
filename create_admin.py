import sqlite3
from werkzeug.security import generate_password_hash
from datetime import datetime

username = "admin"
full_name = "System Administrator"
password = "admin123"

conn = sqlite3.connect("adufarms.db")

conn.execute(
    """
    INSERT INTO users
    (username, full_name, password_hash, role, active, created_at)
    VALUES (?, ?, ?, ?, ?, ?)
    """,
    (
        username,
        full_name,
        generate_password_hash(password),
        "ADMIN",
        1,
        datetime.now().isoformat(timespec="seconds")
    )
)

conn.commit()
conn.close()

print("Admin account created successfully.")
print("Username:", username)
print("Role: ADMIN")