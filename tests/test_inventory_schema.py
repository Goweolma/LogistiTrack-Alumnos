"""Valida que init.sql defina las tablas de Inventory con datos coherentes."""

import re
from pathlib import Path


INIT_SQL = (Path(__file__).resolve().parents[1] / "infrastructure" / "postgres" / "init.sql").read_text(
    encoding="utf-8"
)


def _tables() -> set[str]:
    return set(re.findall(r"CREATE TABLE IF NOT EXISTS (\w+)", INIT_SQL))


def _table_block(table: str) -> str:
    return INIT_SQL.split(f"CREATE TABLE IF NOT EXISTS {table}", 1)[1].split(");", 1)[0]


def test_inventory_tables_are_created():
    assert {"products", "inventory", "processed_events"}.issubset(_tables())


def test_processed_events_guarantees_idempotency():
    block = _table_block("processed_events")
    assert "event_id UUID NOT NULL" in block
    assert "PRIMARY KEY (event_id, service_name)" in block


def test_inventory_reservations_keeps_one_result_per_event():
    block = _table_block("inventory_reservations")
    assert "event_id UUID NOT NULL PRIMARY KEY" in block
    assert "CHECK (status IN ('INVENTORY_RESERVED', 'INVENTORY_REJECTED'))" in block
    assert "CHECK (warehouse IN ('NORTE', 'SUR'))" in block
    assert "result_event JSONB NOT NULL" in block


def test_inventory_only_allows_norte_and_sur():
    assert "CHECK (warehouse IN ('NORTE', 'SUR'))" in _table_block("inventory")


def test_products_insert_matches_table_columns():
    assert "name VARCHAR(120) NOT NULL" in _table_block("products")
    assert "INSERT INTO products (product_id, name, product_description, price)" in INIT_SQL
    rows = re.findall(r"\('PROD-\d+', '[^']+', '[^']+', [\d.]+\)", INIT_SQL)
    assert len(rows) == 3
