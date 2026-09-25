import os
import sqlite3
from datetime import datetime

from werkzeug.security import generate_password_hash

BASE_USERS = {
    "admin": {
        "full_name": os.environ.get("ADUFARMS_ADMIN_FULL_NAME", "Business Administrator"),
        "password": os.environ.get("ADUFARMS_ADMIN_PASSWORD", "Admin@2026!"),
        "role": "ADMIN",
    },
    "manager": {
        "full_name": "Operations Manager",
        "password": os.environ.get("ADUFARMS_MANAGER_PASSWORD", "Manager@2026!"),
        "role": "MANAGER",
    },
    "sales": {
        "full_name": "Sales Officer",
        "password": os.environ.get("ADUFARMS_SALES_PASSWORD", "Sales@2026!"),
        "role": "SALES_OFFICER",
    },
    "inventory": {
        "full_name": "Inventory Officer",
        "password": os.environ.get("ADUFARMS_INVENTORY_PASSWORD", "Inventory@2026!"),
        "role": "INVENTORY_OFFICER",
    },
    "accounts": {
        "full_name": "Accountant",
        "password": os.environ.get("ADUFARMS_ACCOUNTANT_PASSWORD", "Accounts@2026!"),
        "role": "ACCOUNTANT",
    },
}

conn = sqlite3.connect("adufarms.db")
for username, config in BASE_USERS.items():
    password = str(config["password"]).strip() or f"{username.title()}@2026!"
    conn.execute(
        """
        INSERT INTO users
        (username, full_name, password_hash, role, active, created_at)
        VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT(username) DO UPDATE SET
            full_name = excluded.full_name,
            password_hash = excluded.password_hash,
            role = excluded.role,
            active = excluded.active,
            last_login = NULL,
            failed_login_attempts = 0,
            locked_until = NULL
        """,
        (
            username,
            config["full_name"].strip() or username.title(),
            generate_password_hash(password),
            config["role"],
            1,
            datetime.now().isoformat(timespec="seconds"),
        ),
    )
    print(f"{username}: {password} | {config['role']}")

conn.commit()
conn.close()
print("Business accounts ready.")