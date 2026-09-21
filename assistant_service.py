"""Verified, database-backed management assistant for ADUFARMS."""
from __future__ import annotations

from datetime import date, timedelta


def _money(value):
    return f"GH₵{float(value or 0):,.2f}"


def answer_question(conn, question: str) -> dict:
    """Answer supported business questions from current database facts only."""
    text = (question or "").strip().lower()
    today = date.today()
    if not text:
        return {"title": "Ask ADUFARMS", "answer": "Enter a business question to search verified ADUFARMS records.", "facts": []}

    # Stock & Inventory Queries (KG + Bags)
    if ("stock" in text or "inventory" in text or "maize" in text or "bag" in text) and not ("top" in text or "purchase" in text):
        purchased = conn.execute("SELECT COALESCE(SUM(quantity_received_kg),0) FROM purchases WHERE deleted=0").fetchone()[0]
        sold = conn.execute("SELECT COALESCE(SUM(quantity_kg),0) FROM sales WHERE deleted=0").fetchone()[0]
        avail = max(float(purchased) - float(sold), 0.0)
        bags_50 = round(avail / 50)
        bags_100 = round(avail / 100)
        return {
            "title": "Current Stock Position",
            "answer": f"Current available maize stock is {avail:,.2f} KG (~{bags_50:,} bags of 50 KG, or ~{bags_100:,} bags of 100 KG).",
            "facts": [
                f"Total Inbound Purchased: {float(purchased):,.2f} KG",
                f"Total Dispatched Sold: {float(sold):,.2f} KG",
                f"Remaining Stock: {avail:,.2f} KG",
                f"Standard 50kg Bags: ~{bags_50:,}",
                f"Jumbo 100kg Bags: ~{bags_100:,}"
            ]
        }

    # Outstanding Balances / Debtors
    if "owe" in text or "outstanding" in text or "unpaid" in text or "debt" in text or "balance" in text:
        rows = conn.execute("""SELECT c.name, COALESCE(SUM(s.total_sale),0)+c.opening_balance billed,
            COALESCE((SELECT SUM(p.amount) FROM payments p JOIN sales ps ON ps.transaction_id=p.transaction_id
                      WHERE ps.customer_id=c.id AND p.deleted=0),0) paid
            FROM customers c LEFT JOIN sales s ON s.customer_id=c.id AND s.deleted=0
            WHERE c.active=1 GROUP BY c.id ORDER BY (billed-paid) DESC""").fetchall()
        balances = [(r["name"], max(float(r["billed"]) - float(r["paid"]), 0)) for r in rows]
        balances = [(name, value) for name, value in balances if value > 0.005]
        if not balances:
            return {"title": "Outstanding Balances", "answer": "All customer accounts are fully settled. No outstanding balances.", "facts": []}
        total_debt = sum(val for _, val in balances)
        return {
            "title": "Outstanding Customer Balances",
            "answer": f"{len(balances)} customer(s) have outstanding balances totaling {_money(total_debt)}.",
            "facts": [f"{name}: {_money(value)}" for name, value in balances[:10]]
        }

    # Purchases / Procurement / Suppliers
    if "purchase" in text or "supplier" in text or "procurement" in text or "intake" in text:
        p_data = conn.execute("SELECT COALESCE(SUM(quantity_received_kg),0), COALESCE(SUM(total_cost),0), COUNT(DISTINCT local_agent) FROM purchases WHERE deleted=0").fetchone()
        qty, cost, suppliers = float(p_data[0]), float(p_data[1]), int(p_data[2])
        return {
            "title": "Maize Procurement Summary",
            "answer": f"A total of {qty:,.2f} KG of maize has been procured across {suppliers} supplier(s) for a total acquisition cost of {_money(cost)}.",
            "facts": [
                f"Total Inbound Maize: {qty:,.2f} KG",
                f"Total Purchase Cost: {_money(cost)}",
                f"Active Suppliers: {suppliers}",
                f"Average Cost/KG: {_money(cost/qty if qty > 0 else 0)}"
            ]
        }

    # Profit / Financial Position / Revenue
    if "profit" in text or "revenue" in text or "expense" in text or "financial" in text:
        sales_val = conn.execute("SELECT COALESCE(SUM(total_sale),0) FROM sales WHERE deleted=0").fetchone()[0]
        cost_val = conn.execute("SELECT COALESCE(SUM(total_cost),0) FROM purchases WHERE deleted=0").fetchone()[0]
        paid_val = conn.execute("SELECT COALESCE(SUM(amount),0) FROM payments WHERE deleted=0").fetchone()[0]
        gross_profit = float(sales_val) - float(cost_val)
        return {
            "title": "Financial Performance Overview",
            "answer": f"Total sales revenue is {_money(sales_val)} with total acquisition expenses of {_money(cost_val)}, resulting in an estimated gross profit of {_money(gross_profit)}.",
            "facts": [
                f"Gross Sales Revenue: {_money(sales_val)}",
                f"Total Procurement Expenses: {_money(cost_val)}",
                f"Payments Collected: {_money(paid_val)}",
                f"Estimated Gross Margin: {_money(gross_profit)}"
            ]
        }

    # Time-based Activity (Today / Yesterday / Month)
    if "today" in text or "yesterday" in text or "month" in text or "week" in text:
        if "yesterday" in text:
            target = today - timedelta(days=1)
            start = end = target.isoformat()
            label = "yesterday"
        elif "month" in text:
            start = today.replace(day=1).isoformat()
            end = today.isoformat()
            label = "this month"
        elif "week" in text:
            start = (today - timedelta(days=7)).isoformat()
            end = today.isoformat()
            label = "the past 7 days"
        else:
            start = end = today.isoformat()
            label = "today"
        sales = conn.execute("SELECT COALESCE(SUM(total_sale),0), COALESCE(SUM(quantity_kg),0), COUNT(*) FROM sales WHERE deleted=0 AND sale_date BETWEEN ? AND ?", (start, end)).fetchone()
        payments = conn.execute("SELECT COALESCE(SUM(amount),0), COUNT(*) FROM payments WHERE deleted=0 AND payment_date BETWEEN ? AND ?", (start, end)).fetchone()
        purchases = conn.execute("SELECT COALESCE(SUM(total_cost),0), COALESCE(SUM(quantity_received_kg),0), COUNT(*) FROM purchases WHERE deleted=0 AND purchase_date BETWEEN ? AND ?", (start, end)).fetchone()
        return {
            "title": f"Operations Summary for {label.title()}",
            "answer": f"Sales: {_money(sales[0])} ({sales[2]} sale(s), {float(sales[1]):,.2f} KG). Payments: {_money(payments[0])} ({payments[1]} transaction(s)). Purchases: {_money(purchases[0])} ({purchases[2]} intake(s)).",
            "facts": [
                f"Maize Dispatched: {float(sales[1]):,.2f} KG",
                f"Maize Received: {float(purchases[1]):,.2f} KG",
                f"Sales Total: {_money(sales[0])}",
                f"Payments Collected: {_money(payments[0])}",
                f"Period: {start} to {end}"
            ]
        }

    # Top Customers
    if "customer" in text and ("most" in text or "top" in text or "best" in text or "largest" in text):
        rows = conn.execute("""SELECT c.name, COALESCE(SUM(s.total_sale),0) total, COALESCE(SUM(s.quantity_kg),0) qty
            FROM customers c JOIN sales s ON s.customer_id=c.id AND s.deleted=0
            GROUP BY c.id ORDER BY total DESC LIMIT 5""").fetchall()
        return {
            "title": "Top Customers by Volume & Revenue",
            "answer": "Top customer accounts ranked by total billed sales volume:",
            "facts": [f"{r['name']}: {_money(r['total'])} ({float(r['qty']):,.2f} KG)" for r in rows] or ["No sales data is available yet."]
        }

    return {
        "title": "Verified Agribusiness Assistant",
        "answer": "I can answer specific operational questions from your current database records. Try asking one of the suggestions below.",
        "facts": [
            "Current stock in KG and standard bags",
            "Outstanding customer balances and debtor totals",
            "Today's, yesterday's, or monthly sales and payments",
            "Total maize procurement and supplier acquisition costs",
            "Estimated gross profit and financial position",
            "Top customers ranked by sales volume"
        ]
    }
