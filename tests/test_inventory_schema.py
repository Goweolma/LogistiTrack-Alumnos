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


def test_orders_has_optional_delivery_columns():
    block = _table_block("orders")
    assert re.search(r"driver_id VARCHAR\(20\)\s*,", block)
    assert re.search(r"vehicle_id VARCHAR\(20\)\s*,", block)


def test_order_history_has_optional_event_columns_for_delivery():
    block = _table_block("order_history")
    assert re.search(r"event_id UUID UNIQUE\s*,", block)
    assert re.search(r"event JSONB\s*$", block)


def test_order_ids_come_from_a_bounded_sequence():
    sequence = "CREATE SEQUENCE IF NOT EXISTS order_number_seq MINVALUE 1 MAXVALUE 999999 NO CYCLE;"
    assert sequence in INIT_SQL
    assert INIT_SQL.index(sequence) < INIT_SQL.index("CREATE TABLE IF NOT EXISTS orders")
    assert (
        "order_id VARCHAR(40) PRIMARY KEY DEFAULT ('PED-' || lpad(nextval('order_number_seq')::text, 6, '0'))"
        in _table_block("orders")
    )


def test_inventory_only_allows_norte_and_sur():
    assert "CHECK (warehouse IN ('NORTE', 'SUR'))" in _table_block("inventory")


def test_products_insert_matches_table_columns():
    assert "name VARCHAR(120) NOT NULL" in _table_block("products")
    assert "INSERT INTO products (product_id, name, product_description, price)" in INIT_SQL
    rows = re.findall(r"\('PROD-\d+', '[^']+', '[^']+', [\d.]+\)", INIT_SQL)
    assert len(rows) == 3
