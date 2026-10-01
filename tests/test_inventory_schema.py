"""Valida que init.sql defina solo las tablas de Inventory y datos coherentes."""

import re
from pathlib import Path


INIT_SQL = (Path(__file__).resolve().parents[1] / "infrastructure" / "postgres" / "init.sql").read_text(
    encoding="utf-8"
)


def _tables() -> set[str]:
    return set(re.findall(r"CREATE TABLE IF NOT EXISTS (\w+)", INIT_SQL))


def test_only_inventory_tables_are_created():
    assert _tables() == {"products", "inventory", "processed_events"}


def test_processed_events_guarantees_idempotency():
    block = INIT_SQL.split("CREATE TABLE IF NOT EXISTS processed_events", 1)[1].split(");", 1)[0]
    assert "event_id" in block
    assert "PRIMARY KEY (event_id, consumer)" in block


def test_products_insert_matches_table_columns():
    assert "INSERT INTO products (product_id, product_name, product_description, price)" in INIT_SQL
    rows = re.findall(r"\('PROD-\d+', '[^']+', '[^']+', [\d.]+\)", INIT_SQL)
    assert len(rows) == 3
