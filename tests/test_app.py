import os
import sqlite3
from pathlib import Path

import pytest
from werkzeug.security import generate_password_hash

TEST_DATABASE = Path(__file__).resolve().parent / "test-adufarms.db"
os.environ["DATABASE_PATH"] = str(TEST_DATABASE)
os.environ["ADUFARMS_SECRET_KEY"] = "test-secret-key"

import app as application
import backup_service
from stock_service import assert_stock_available, available_stock


@pytest.fixture(scope="session", autouse=True)
def initialized_database():
    if TEST_DATABASE.exists():
        TEST_DATABASE.unlink()
    application.init_db()
    yield
    if TEST_DATABASE.exists():
        TEST_DATABASE.unlink()


@pytest.fixture
def client():
    application.app.config.update(TESTING=True, WTF_CSRF_ENABLED=False)
    with application.app.test_client() as test_client:
        yield test_client


def seed_admin():
    conn = application.db()
    conn.execute(
        "INSERT OR IGNORE INTO users(username,full_name,password_hash,role,active,created_at) VALUES(?,?,?,?,?,?)",
        ("admin", "Test Admin", generate_password_hash("StrongPassword1!"), "ADMIN", 1, application.now()),
    )
    conn.execute("UPDATE users SET role='ADMIN',active=1 WHERE username='admin'")
    conn.commit()
    conn.close()


def login_session(client):
    with client.session_transaction() as session:
        session.update(user_id=1, username="admin", full_name="Test Admin", role="ADMIN")


def test_route_endpoints_build_without_errors():
    with application.app.test_request_context():
        for rule in application.app.url_map.iter_rules():
            if "<" not in rule.rule:
                application.url_for(rule.endpoint)


def test_invoice_status_boundaries():
    assert application.invoice_status_for(100, 0) == "UNPAID"
    assert application.invoice_status_for(100, 25) == "PART PAYMENT"
    assert application.invoice_status_for(100, 100) == "PAID"
    assert application.invoice_status_for(100, 101) == "OVERPAID"


def test_stock_service_rejects_sales_above_available_stock():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript(
        "CREATE TABLE purchases(quantity_received_kg REAL, deleted INTEGER);"
        "CREATE TABLE sales(quantity_kg REAL, deleted INTEGER);"
    )
    conn.execute("INSERT INTO purchases VALUES(100, 0)")
    conn.execute("INSERT INTO sales VALUES(40, 0)")
    assert available_stock(conn) == 60
    with pytest.raises(ValueError, match="Insufficient stock"):
        assert_stock_available(conn, 61)
    conn.close()


def test_dashboard_includes_customer_opening_balance(client):
    seed_admin()
    conn = application.db()
    conn.execute(
        "INSERT INTO customers(name,phone,opening_balance,created_at) VALUES(?,?,?,?)",
        ("Opening Balance Customer", "000", 125, application.now()),
    )
    conn.commit()
    conn.close()
    login_session(client)
    response = client.get("/dashboard")
    assert response.status_code == 200
    assert b"GHS 125.00" in response.data


def test_login_requires_csrf_token(client):
    response = client.post("/login", data={"username": "admin", "password": "wrong"})
    assert response.status_code == 400


def test_session_role_is_refreshed_and_deactivated_users_are_logged_out(client):
    conn = application.db()
    conn.execute("UPDATE users SET role='ADMINISTRATOR' WHERE id=1")
    conn.commit()
    conn.close()
    login_session(client)
    assert client.get("/dashboard").status_code == 200

    conn = application.db()
    conn.execute("UPDATE users SET active=0 WHERE id=1")
    conn.commit()
    conn.close()
    assert client.get("/dashboard").status_code == 302


def test_viewer_cannot_read_customer_or_transaction_details(client):
    conn = application.db()
    conn.execute("UPDATE users SET active=1,role='VIEWER' WHERE id=1")
    customer_id = conn.execute(
        "INSERT INTO customers(name,phone,opening_balance,created_at) VALUES(?,?,?,?)",
        ("Private Customer", "111", 0, application.now()),
    ).lastrowid
    conn.commit()
    conn.close()
    with client.session_transaction() as session:
        session.update(user_id=1, username="admin", full_name="Test Admin", role="VIEWER")
    assert client.get(f"/customers/{customer_id}").status_code == 403
    assert client.get("/search?q=Private").status_code == 403


def test_invoice_opens_payment_collection_for_unpaid_sale(client):
    seed_admin()
    conn = application.db()
    conn.execute("UPDATE users SET active=1,role='ADMIN' WHERE id=1")
    customer_id = conn.execute(
        "INSERT INTO customers(name,phone,created_at) VALUES(?,?,?)",
        ("Payment Customer", "222", application.now()),
    ).lastrowid
    conn.execute(
        "INSERT INTO sales(transaction_id,sales_id,invoice_number,sale_date,customer_id,quantity_kg,selling_price_kg,total_sale,staff_user,created_at) VALUES(?,?,?,?,?,?,?,?,?,?)",
        ("ADU-TEST-1", "ADU-SAL-TEST-1", "ADU-INV-TEST-1", "2026-09-22", customer_id, 10, 5, 50, "admin", application.now()),
    )
    conn.execute(
        "INSERT INTO invoices(invoice_number,transaction_id,sales_id,invoice_date,generated_by,generated_at) VALUES(?,?,?,?,?,?)",
        ("ADU-INV-TEST-1", "ADU-TEST-1", "ADU-SAL-TEST-1", "2026-09-22", "admin", application.now()),
    )
    conn.commit()
    conn.close()
    login_session(client)

    invoice_response = client.get("/invoice/ADU-SAL-TEST-1")
    assert invoice_response.status_code == 200
    assert b"Record payment" in invoice_response.data
    assert b"payments?customer_id=" in invoice_response.data

    payment_response = client.get(
        "/payments?customer_id=%s&sales_id=ADU-SAL-TEST-1" % customer_id
    )
    assert payment_response.status_code == 200
    assert b"ADU-SAL-TEST-1" in payment_response.data


def test_customer_creation_rejects_duplicate_normalized_identity(client):
    seed_admin()
    login_session(client)
    conn = application.db()
    conn.execute(
        "INSERT INTO customers(name,phone,created_at) VALUES(?,?,?)",
        ("Lord Sekyi", "059 905 5062", application.now()),
    )
    conn.commit()
    before = conn.execute("SELECT COUNT(*) FROM customers").fetchone()[0]
    conn.close()
    with client.session_transaction() as session:
        session["csrf_token"] = "duplicate-test-csrf"
    response = client.post("/customers", data={
        "csrf_token": "duplicate-test-csrf",
        "name": "  lord   sekyi ",
        "phone": "059-905-5062",
        "opening_balance": "0",
        "customer_type": "RETAIL",
    })
    assert response.status_code == 200
    assert b"This customer already exists" in response.data
    conn = application.db()
    assert conn.execute("SELECT COUNT(*) FROM customers").fetchone()[0] == before
    conn.close()


def test_backup_restore_verifies_and_preserves_safety_copy(tmp_path, monkeypatch):
    source = tmp_path / "source.db"
    backup_dir = tmp_path / "backups"
    backup_dir.mkdir()
    conn = sqlite3.connect(source)
    conn.execute("CREATE TABLE marker(value TEXT NOT NULL)")
    conn.execute("INSERT INTO marker VALUES('original')")
    conn.commit()
    conn.close()
    monkeypatch.setattr(backup_service, "BACKUP_DIR", backup_dir)

    backup = backup_service.create_backup(source)
    assert backup.with_suffix(".json").exists()
    backup_service.verify_backup(backup)
    conn = sqlite3.connect(source)
    conn.execute("UPDATE marker SET value='changed'")
    conn.commit()
    conn.close()

    safety_backup = backup_service.safe_restore(source, backup.name)
    conn = sqlite3.connect(source)
    assert conn.execute("SELECT value FROM marker").fetchone()[0] == "original"
    conn.close()
    assert safety_backup.exists()
    backup_service.verify_database(safety_backup)
