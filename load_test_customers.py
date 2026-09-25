import time
from pathlib import Path

import app as application
from werkzeug.security import generate_password_hash


def ensure_database():
    # Create schema if the app database has not been initialized yet.
    application.init_db()


def add_customers(count: int = 5000):
    conn = application.db()
    try:
        conn.execute(
            "INSERT OR IGNORE INTO users(username, full_name, password_hash, role, active, created_at) VALUES(?,?,?,?,?,?)",
            ("admin", "Admin User", generate_password_hash("StrongPassword1!"), "ADMIN", 1, application.now()),
        )
        conn.commit()

        existing = conn.execute("SELECT COUNT(*) AS c FROM customers").fetchone()["c"]
        if existing >= count:
            print(f"Customers already present: {existing}. No new inserts needed.")
            return existing

        rows = []
        ts = application.now()
        for i in range(count - existing):
            phone = f"233{(100000000 + i) % 900000000 + 100000000}"
            rows.append((f"Customer {existing + i + 1}", phone, "", "", "RETAIL", 0.0, "", ts))

        conn.executemany(
            "INSERT INTO customers(name, phone, address, location, customer_type, opening_balance, notes, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            rows,
        )
        conn.commit()
        total = conn.execute("SELECT COUNT(*) AS c FROM customers").fetchone()["c"]
        print(f"Inserted {total - existing} customers. Total now: {total}.")
        return total
    finally:
        conn.close()


def validate_routes():
    conn = application.db()
    admin = conn.execute("SELECT id, username, full_name FROM users WHERE username=? AND active=1 LIMIT 1", ("admin",)).fetchone()
    conn.close()
    admin_id = admin["id"] if admin else None

    with application.app.test_client() as client:
        with client.session_transaction() as session:
            if admin_id is not None:
                session.update(user_id=admin_id, username="admin", full_name="Admin User", role="ADMIN")

        routes = [
            "/dashboard",
            "/customers",
            "/sales",
            "/payments",
            "/invoice",
            "/reports",
            "/stock",
            "/search?q=Customer+1",
        ]

        results = []
        for route in routes:
            start = time.perf_counter()
            response = client.get(route)
            elapsed = time.perf_counter() - start
            results.append((route, response.status_code, elapsed))

        for route, status, elapsed in results:
            print(f"{route} -> {status} in {elapsed:.4f}s")

        print("All route checks completed.")


if __name__ == "__main__":
    ensure_database()
    total = add_customers(5000)
    print(f"Final customer count: {total}")
    validate_routes()
