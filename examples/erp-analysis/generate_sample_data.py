"""Generate a small, seeded ERP sample dataset (order-to-cash).

Schema mirrors real Kaggle ERP/supply-chain datasets (e.g. fares279/messyops,
ayodejiibrahimlateef/supply-chain-datasets) so you can drop real CSVs in with
minimal column remapping. See README for the mapping.

Tables: customers, products, sales_orders, sales_order_lines.
"""

import csv
import os
import random
from datetime import date, timedelta

REGIONS = ["East", "West", "North", "South"]
CATEGORIES = ["Furniture", "Technology", "Office Supplies"]
SEGMENTS = ["Consumer", "Corporate", "Home Office"]
INDUSTRIES = ["Retail", "Manufacturing", "Healthcare", "Finance", "Education"]
CHANNELS = ["Online", "Partner", "Direct"]


def generate(out_dir: str, seed: int = 42):
    rng = random.Random(seed)
    os.makedirs(out_dir, exist_ok=True)

    # customers
    customers = []
    for i in range(1, 201):
        customers.append({
            "customer_id": f"C{i:04d}",
            "name": f"Customer {i}",
            "industry": rng.choice(INDUSTRIES),
            "segment": rng.choice(SEGMENTS),
            "region": rng.choice(REGIONS),
        })
    _write(out_dir, "customers.csv", customers)

    # products
    products = []
    for i in range(1, 61):
        cat = rng.choice(CATEGORIES)
        cost = round(rng.uniform(20, 400), 2)
        margin = {"Furniture": 1.35, "Technology": 1.55, "Office Supplies": 1.25}[cat]
        products.append({
            "product_id": f"P{i:04d}",
            "name": f"{cat[:4]}-Item-{i}",
            "category": cat,
            "unit_cost": cost,
            "unit_price": round(cost * margin, 2),
        })
    _write(out_dir, "products.csv", products)

    prod_by_id = {p["product_id"]: p for p in products}
    cust_by_id = {c["customer_id"]: c for c in customers}

    # sales_orders + lines over 2024-2025
    start = date(2024, 1, 1)
    orders, lines = [], []
    line_id = 1
    for oid in range(1, 1801):
        cust = rng.choice(customers)
        day_offset = rng.randint(0, 729)
        odate = start + timedelta(days=day_offset)
        region = cust["region"]
        orders.append({
            "order_id": f"SO{oid:05d}",
            "customer_id": cust["customer_id"],
            "order_date": odate.isoformat(),
            "channel": rng.choice(CHANNELS),
            "status": rng.choices(["Completed", "Cancelled"], weights=[0.93, 0.07])[0],
            "region": region,
        })
        for _ in range(rng.randint(1, 4)):
            p = rng.choice(products)
            qty = rng.randint(1, 12)
            # Signal: West + Technology gets deeper discounts in 2025 -> margin erosion
            base_disc = rng.uniform(0, 0.15)
            if region == "West" and p["category"] == "Technology" and odate.year == 2025:
                base_disc += rng.uniform(0.15, 0.30)
            disc = round(min(base_disc, 0.5), 3)
            unit_price = p["unit_price"]
            line_total = round(qty * unit_price * (1 - disc), 2)
            cogs = round(qty * p["unit_cost"], 2)
            lines.append({
                "line_id": f"L{line_id:06d}",
                "order_id": f"SO{oid:05d}",
                "product_id": p["product_id"],
                "quantity": qty,
                "unit_price": unit_price,
                "discount": disc,
                "line_total": line_total,
                "cogs": cogs,
                "profit": round(line_total - cogs, 2),
            })
            line_id += 1

    # A few extreme outliers for anomaly detection to surface
    for _ in range(6):
        ln = rng.choice(lines)
        ln["line_total"] = round(ln["line_total"] * rng.uniform(15, 30), 2)
        ln["profit"] = round(ln["line_total"] - ln["cogs"], 2)

    _write(out_dir, "sales_orders.csv", orders)
    _write(out_dir, "sales_order_lines.csv", lines)
    return {"customers": len(customers), "products": len(products),
            "orders": len(orders), "lines": len(lines)}


def _write(out_dir, name, rows):
    path = os.path.join(out_dir, name)
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)


if __name__ == "__main__":
    here = os.path.dirname(os.path.abspath(__file__))
    stats = generate(os.path.join(here, "data"))
    print("Generated ERP sample:", stats)
