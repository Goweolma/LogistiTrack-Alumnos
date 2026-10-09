"""Valida en init.sql las cuentas de usuario, el catálogo de tamaños y el tamaño guardado en el pedido.

SCHEMA_TEST_DATABASE_URL habilita las pruebas con PostgreSQL real en un esquema temporal
que se revierte al terminar; sin esa variable solo corren las pruebas sobre el texto de init.sql.
"""

import os
import re
from pathlib import Path

import psycopg
import pytest
from psycopg import errors, sql
from uuid import uuid4


INIT_SQL = (Path(__file__).resolve().parents[1] / "infrastructure" / "postgres" / "init.sql").read_text(
    encoding="utf-8"
)

PACKAGE_ROW = re.compile(
    r"\('(PKG-[A-Z]+)', '([^']+)', ([\d.]+), ([\d.]+), ([\d.]+), ([\d.]+), ([\d.]+)\)"
)


def _table_block(table: str) -> str:
    return INIT_SQL.split(f"CREATE TABLE IF NOT EXISTS {table} (", 1)[1].split(");", 1)[0]


def _package_rows() -> list[tuple]:
    return [
        (pid, name, *map(float, numbers))
        for pid, name, *numbers in PACKAGE_ROW.findall(INIT_SQL)
    ]


# --- Texto de init.sql -------------------------------------------------------


def test_users_has_required_columns_and_defaults():
    block = _table_block("users")
    assert "user_id SERIAL PRIMARY KEY" in block
    assert "email VARCHAR(254) NOT NULL" in block
    assert "name VARCHAR(120) NOT NULL" in block
    assert re.search(r"phone VARCHAR\(20\)", block)
    assert re.search(r"address VARCHAR\(200\)\s*,", block)
    assert "role VARCHAR(10) NOT NULL DEFAULT 'user' CHECK (role IN ('user', 'admin'))" in block
    assert "created_at TIMESTAMPTZ NOT NULL DEFAULT now()" in block
    assert "is_active BOOLEAN NOT NULL DEFAULT TRUE" in block


def test_users_email_is_unique_ignoring_case():
    assert "CREATE UNIQUE INDEX IF NOT EXISTS users_email_unique ON users (lower(email));" in INIT_SQL


def test_package_sizes_has_required_columns():
    block = _table_block("package_sizes")
    assert "package_size_id VARCHAR(20) NOT NULL PRIMARY KEY" in block
    assert "name VARCHAR(60) NOT NULL UNIQUE" in block
    for column in ("length_cm", "width_cm", "height_cm"):
        assert f"{column} NUMERIC(6, 1) NOT NULL CHECK ({column} > 0)" in block
    assert "max_weight_kg NUMERIC(6, 2) NOT NULL CHECK (max_weight_kg > 0)" in block
    assert "price NUMERIC(10, 2) NOT NULL CHECK (price >= 0)" in block
    assert "is_active BOOLEAN NOT NULL DEFAULT TRUE" in block


def test_package_sizes_is_created_before_orders():
    assert INIT_SQL.index("CREATE TABLE IF NOT EXISTS package_sizes") < INIT_SQL.index(
        "CREATE TABLE IF NOT EXISTS orders"
    )


def test_catalog_has_five_valid_sizes():
    rows = _package_rows()

    assert len(rows) == 5
    assert len({row[0] for row in rows}) == 5
    assert len({row[1] for row in rows}) == 5
    for _, _, length, width, height, max_weight, price in rows:
        assert min(length, width, height, max_weight) > 0
        assert price >= 0


def test_catalog_sizes_grow_in_weight_and_price():
    rows = _package_rows()
    weights = [row[5] for row in rows]
    prices = [row[6] for row in rows]

    assert weights == sorted(weights) and len(set(weights)) == 5
    assert prices == sorted(prices) and len(set(prices)) == 5


def test_orders_stores_package_size_and_confirmed_price():
    block = _table_block("orders")
    assert "package_size_id VARCHAR(20) REFERENCES package_sizes(package_size_id)," in block
    assert "confirmed_price NUMERIC(10, 2) CHECK (confirmed_price >= 0)," in block
    assert "CHECK ((package_size_id IS NULL) = (confirmed_price IS NULL))" in block
    # delivery_address ya existía; el pedido sigue guardándola.
    assert "delivery_address VARCHAR(200) NOT NULL" in block


# --- PostgreSQL real ---------------------------------------------------------


@pytest.fixture
def db():
    url = os.getenv("SCHEMA_TEST_DATABASE_URL")
    if not url:
        pytest.skip("Configura SCHEMA_TEST_DATABASE_URL para probar PostgreSQL")

    with psycopg.connect(url, autocommit=True) as connection:
        # Todo, incluido el esquema temporal, se revierte incluso si falla la prueba.
        with connection.transaction(force_rollback=True):
            schema = "schema_test_" + uuid4().hex
            connection.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(schema)))
            connection.execute(sql.SQL("SET LOCAL search_path TO {}").format(sql.Identifier(schema)))
            connection.execute(INIT_SQL)
            yield connection


def _rejects(connection, error, query, params=()):
    with pytest.raises(error):
        with connection.transaction():
            connection.execute(query, params)


def test_db_registration_creates_active_user_accounts(db):
    role, is_active, created_at = db.execute(
        "INSERT INTO users (email, name) VALUES ('ana@correo.com', 'Ana') RETURNING role, is_active, created_at"
    ).fetchone()

    assert (role, is_active) == ("user", True)
    assert created_at is not None


def test_db_admin_is_only_assigned_explicitly(db):
    db.execute("INSERT INTO users (email, name) VALUES ('ana@correo.com', 'Ana')")
    db.execute("UPDATE users SET role = 'admin' WHERE email = 'ana@correo.com'")

    assert db.execute("SELECT role FROM users").fetchone() == ("admin",)
    _rejects(db, errors.CheckViolation, "UPDATE users SET role = 'superadmin'")


@pytest.mark.parametrize(
    ("columns", "values"),
    [
        ("email, name", ("sin-arroba", "Ana")),
        ("email, name", ("ana@correo", "Ana")),
        ("email, name", ("ana@correo.com", "   ")),
        ("email, name, phone", ("ana@correo.com", "Ana", "55-ABC")),
        ("email, name, role", ("ana@correo.com", "Ana", "root")),
    ],
)
def test_db_rejects_invalid_user_data(db, columns, values):
    placeholders = ", ".join(["%s"] * len(values))
    _rejects(db, errors.CheckViolation, f"INSERT INTO users ({columns}) VALUES ({placeholders})", values)


def test_db_rejects_duplicate_email_ignoring_case(db):
    db.execute("INSERT INTO users (email, name, phone) VALUES ('ana@correo.com', 'Ana', '+525512345678')")

    _rejects(db, errors.UniqueViolation, "INSERT INTO users (email, name) VALUES ('ANA@correo.com', 'Otra Ana')")


def test_db_catalog_has_five_active_sizes(db):
    rows = db.execute("SELECT package_size_id, is_active FROM package_sizes ORDER BY max_weight_kg").fetchall()

    assert [pid for pid, _ in rows] == ["PKG-XS", "PKG-S", "PKG-M", "PKG-L", "PKG-XL"]
    assert all(active for _, active in rows)


def test_db_rejects_invalid_package_sizes(db):
    insert = (
        "INSERT INTO package_sizes (package_size_id, name, length_cm, width_cm, height_cm, max_weight_kg, price) "
        "VALUES (%s, %s, %s, %s, %s, %s, %s)"
    )
    _rejects(db, errors.CheckViolation, insert, ("PKG-Z", "Cero", 0, 10, 10, 1, 50))
    _rejects(db, errors.CheckViolation, insert, ("PKG-Z", "Sin peso", 10, 10, 10, 0, 50))
    _rejects(db, errors.CheckViolation, insert, ("PKG-Z", "Negativo", 10, 10, 10, 1, -1))
    _rejects(db, errors.UniqueViolation, insert, ("PKG-Z", "Sobre", 10, 10, 10, 1, 50))


def test_db_order_keeps_size_address_and_confirmed_price(db):
    order_id = db.execute(
        """
        INSERT INTO orders (total, delivery_address, package_size_id, confirmed_price)
        SELECT price, 'Av. Universidad 100', package_size_id, price FROM package_sizes WHERE package_size_id = 'PKG-M'
        RETURNING order_id
        """
    ).fetchone()[0]

    # El precio confirmado no cambia si después se actualiza el catálogo.
    db.execute("UPDATE package_sizes SET price = 999 WHERE package_size_id = 'PKG-M'")
    row = db.execute(
        "SELECT package_size_id, delivery_address, confirmed_price FROM orders WHERE order_id = %s", (order_id,)
    ).fetchone()

    assert order_id == "PED-000001"
    assert (row[0], row[1], float(row[2])) == ("PKG-M", "Av. Universidad 100", 189.0)


def test_db_order_rejects_incomplete_or_unknown_size(db):
    insert = "INSERT INTO orders (total, delivery_address, package_size_id, confirmed_price) VALUES (0, 'Av. Demo', %s, %s)"
    _rejects(db, errors.CheckViolation, insert, ("PKG-M", None))
    _rejects(db, errors.CheckViolation, insert, (None, 189))
    _rejects(db, errors.CheckViolation, insert, ("PKG-M", -1))
    _rejects(db, errors.ForeignKeyViolation, insert, ("PKG-NOPE", 189))


def test_db_orders_without_size_keep_working(db):
    # Orders todavía crea pedidos por productos (services/orders/app.py) y no envía tamaño.
    db.execute("INSERT INTO orders (total, delivery_address, status) VALUES (0, 'Av. Demo', 'RECEIVED')")

    assert db.execute("SELECT package_size_id, confirmed_price FROM orders").fetchone() == (None, None)
