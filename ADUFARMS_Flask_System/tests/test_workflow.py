import os
import sys
import unittest
from pathlib import Path


TEST_DIR = Path(__file__).parent / "_test_runtime"
TEST_DIR.mkdir(exist_ok=True)
TEST_DB = TEST_DIR / "test.db"
if TEST_DB.exists():
    TEST_DB.unlink()
os.environ["DATABASE_PATH"] = str(TEST_DB)
sys.path.insert(0, str(Path(__file__).parents[1] / "ADUFARMS"))

import app as application


class SalesWorkflowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        application.init_db()
        conn = application.db()
        cls.customer_a = conn.execute(
            "INSERT INTO customers(name,phone,created_at) VALUES(?,?,?)",
            ("Customer A", "0500000001", application.now()),
        ).lastrowid
        cls.customer_b = conn.execute(
            "INSERT INTO customers(name,phone,created_at) VALUES(?,?,?)",
            ("Customer B", "0500000002", application.now()),
        ).lastrowid
        conn.execute(
            "INSERT INTO purchases(purchase_id,purchase_date,local_agent,quantity_kg,price_per_kg,total_purchase_cost,total_cost,quantity_received_kg,staff_user,created_at) VALUES(?,?,?,?,?,?,?,?,?,?)",
            ("ADU-PUR-20260914-0001", "2026-09-14", "Supplier", 100, 10, 1000, 1000, 100, "tester", application.now()),
        )
        conn.execute(
            "INSERT INTO sales(transaction_id,sales_id,invoice_number,sale_date,customer_id,quantity_kg,selling_price_kg,total_sale,staff_user,created_at) VALUES(?,?,?,?,?,?,?,?,?,?)",
            ("ADU-20260914-0001", "SALE-20260914-0001", "ADU-INV-20260914-0001", "2026-09-14", cls.customer_a, 10, 20, 200, "tester", application.now()),
        )
        conn.execute(
            "INSERT INTO sales(transaction_id,sales_id,invoice_number,sale_date,customer_id,quantity_kg,selling_price_kg,total_sale,staff_user,created_at) VALUES(?,?,?,?,?,?,?,?,?,?)",
            ("ADU-20260914-0002", "SALE-20260914-0002", "ADU-INV-20260914-0002", "2026-09-14", cls.customer_b, 10, 30, 300, "tester", application.now()),
        )
        conn.execute(
            "INSERT INTO payments(payment_id,transaction_id,sales_id,payment_date,amount,payment_method,staff_user,created_at) VALUES(?,?,?,?,?,?,?,?)",
            ("ADU-PAY-20260914-0001", "ADU-20260914-0002", "SALE-20260914-0002", "2026-09-14", 50, "Cash", "tester", application.now()),
        )
        conn.commit()
        conn.close()

    def test_daily_ids_are_sequential_and_authoritative(self):
        conn = application.db()
        self.assertEqual(
            application.next_daily_id("SALE", "sales", "sales_id", conn, application.date(2026, 9, 14)),
            "SALE-20260914-0003",
        )
        self.assertEqual(
            application.next_daily_id("ADU-PAY", "payments", "payment_id", conn, application.date(2026, 9, 14)),
            "ADU-PAY-20260914-0002",
        )
        conn.close()

    def test_payment_lookup_cannot_cross_match_another_sale(self):
        with application.app.test_request_context():
            application.session["role"] = "STAFF"
            info = application.sale_info("ADU-PAY-20260914-0001")
        self.assertIsNotNone(info)
        self.assertEqual(info["sales_id"], "SALE-20260914-0002")
        self.assertEqual(info["transaction_id"], "ADU-20260914-0002")

    def test_identifier_relationships_are_persistent(self):
        conn = application.db()
        row = conn.execute(
            """SELECT s.sales_id, s.invoice_number, s.transaction_id, p.payment_id
               FROM sales s JOIN payments p ON p.transaction_id=s.transaction_id
               WHERE s.transaction_id=?""",
            ("ADU-20260914-0002",),
        ).fetchone()
        conn.close()
        self.assertEqual(tuple(row), (
            "SALE-20260914-0002",
            "ADU-INV-20260914-0002",
            "ADU-20260914-0002",
            "ADU-PAY-20260914-0001",
        ))

    def test_date_format_is_portable(self):
        self.assertEqual(application.pretty_date("2026-09-04"), "4 September 2026")
        self.assertEqual(application.pretty_date("2026-09-04 13:05:00"), "4 September 2026 01:05 PM")

    def test_weighted_average_cogs_only_expenses_stock_that_was_sold(self):
        conn = application.db()
        summary = application.cogs_summary(conn)
        conn.close()
        # 100 KG at GH₵10/kg was received; only 20 KG was sold.
        self.assertEqual(round(summary["cogs"], 2), 200.00)
        self.assertEqual(round(summary["inventory_value"], 2), 800.00)


class HttpWorkflowTests(unittest.TestCase):
    """Exercise the protected browser workflow against real Flask routes."""

    def setUp(self):
        conn = application.db()
        for table in ("reversals", "stock_movements", "payments", "invoices", "sales", "purchases", "customers", "audit_log"):
            conn.execute(f"DELETE FROM {table}")
        conn.commit()
        conn.close()
        self.client = application.app.test_client()
        with self.client.session_transaction() as session:
            session["user_id"] = 1
            session["username"] = "workflow-admin"
            session["full_name"] = "Workflow Admin"
            session["role"] = "ADMIN"
            session["csrf_token"] = "workflow-csrf"

    @property
    def csrf(self):
        return "workflow-csrf"

    def sale_info(self, sales_id):
        with application.app.test_request_context():
            application.session["role"] = "ADMIN"
            return application.sale_info(sales_id)

    def test_purchase_sale_payment_reverse_and_restore(self):
        response = self.client.post("/purchases", data={
            "csrf_token": self.csrf, "purchase_date": "2026-09-15", "local_agent": "Supplier A",
            "quantity_kg": "100", "quantity_received_kg": "100", "price_per_kg": "10",
            "transport_cost": "20", "other_expenses": "5",
        })
        self.assertEqual(response.status_code, 302)
        self.assertEqual(application.stock_summary()[2], 100.0)

        response = self.client.post("/sales", data={
            "csrf_token": self.csrf, "sale_date": "2026-09-15", "customer_name": "Customer A",
            "customer_phone": "0500000001", "quantity_kg": "20", "selling_price_kg": "15",
        })
        self.assertEqual(response.status_code, 302)
        self.assertEqual(application.stock_summary()[2], 80.0)
        conn = application.db()
        sale = conn.execute("SELECT id,sales_id,transaction_id,customer_id FROM sales").fetchone()
        invoice = conn.execute("SELECT invoice_number FROM invoices WHERE transaction_id=?", (sale["transaction_id"],)).fetchone()
        conn.close()
        self.assertIsNotNone(invoice)

        response = self.client.post("/payments", data={
            "csrf_token": self.csrf, "customer_id": str(sale["customer_id"]), "sales_id": sale["sales_id"],
            "payment_date": "2026-09-15", "amount": "120", "payment_method": "Mobile Money",
            "payment_reference": "MOMO-001", "notes": "Partial payment",
        })
        self.assertEqual(response.status_code, 302)
        info = self.sale_info(sale["sales_id"])
        self.assertEqual(info["balance"], 180.0)

        response = self.client.post(f"/records/sales/{sale['id']}/reverse", data={
            "csrf_token": self.csrf, "reason": "Customer order cancelled",
        })
        self.assertEqual(response.status_code, 302)
        self.assertEqual(application.stock_summary()[2], 100.0)
        conn = application.db()
        self.assertEqual(conn.execute("SELECT deleted FROM sales WHERE id=?", (sale["id"],)).fetchone()["deleted"], 1)
        self.assertEqual(conn.execute("SELECT deleted FROM payments WHERE transaction_id=?", (sale["transaction_id"],)).fetchone()["deleted"], 1)
        conn.close()

        response = self.client.post(f"/records/sales/{sale['id']}/restore", data={
            "csrf_token": self.csrf,
        })
        self.assertEqual(response.status_code, 302)
        self.assertEqual(application.stock_summary()[2], 80.0)
        info = self.sale_info(sale["sales_id"])
        self.assertEqual(info["balance"], 180.0)

    def test_staff_cannot_access_admin_routes(self):
        with self.client.session_transaction() as session:
            session["role"] = "STAFF"
        self.assertEqual(self.client.get("/admin/users").status_code, 403)
        self.assertEqual(self.client.get("/admin/gallery").status_code, 403)


if __name__ == "__main__":
    unittest.main()
