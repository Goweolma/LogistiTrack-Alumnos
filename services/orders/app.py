"""API base de pedidos. Responsable: Alumno 1."""

import logging
import os
import re
from functools import wraps

from flask import Flask, jsonify, request, session
from common.database import get_connection
from common.events import build_event
from common.kafka_client import create_producer, publish
from werkzeug.security import check_password_hash, generate_password_hash


app = Flask(__name__)
app.config.update(
    SECRET_KEY=os.getenv("SESSION_SECRET", "local-only-change-this-secret"),
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=os.getenv("COOKIE_SECURE", "false").lower() == "true",
)


def ensure_auth_schema():
    """Crea/actualiza las tablas de cuentas también en volúmenes ya existentes."""
    with get_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    user_id SERIAL PRIMARY KEY,
                    email VARCHAR(254) NOT NULL,
                    name VARCHAR(120) NOT NULL,
                    phone VARCHAR(20),
                    address VARCHAR(200),
                    role VARCHAR(10) NOT NULL DEFAULT 'user' CHECK (role IN ('user', 'admin')),
                    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                    is_active BOOLEAN NOT NULL DEFAULT TRUE,
                    password_hash VARCHAR(255) NOT NULL
                )
            """)
            cursor.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS password_hash VARCHAR(255)")
            cursor.execute("CREATE UNIQUE INDEX IF NOT EXISTS users_email_unique ON users (lower(email))")
            cursor.execute("SELECT to_regclass('public.orders')")
            if cursor.fetchone()[0] is not None:
                cursor.execute("ALTER TABLE orders ADD COLUMN IF NOT EXISTS user_id INTEGER REFERENCES users(user_id)")
            admin_email = os.getenv("INITIAL_ADMIN_EMAIL", "").strip().lower()
            admin_password = os.getenv("INITIAL_ADMIN_PASSWORD", "")
            if admin_email and admin_password:
                cursor.execute("SELECT 1 FROM users WHERE lower(email) = %s", (admin_email,))
                if cursor.fetchone() is None:
                    cursor.execute(
                        """INSERT INTO users (email, name, role, password_hash)
                           VALUES (%s, 'Administrador', 'admin', %s)
                           ON CONFLICT DO NOTHING""",
                        (admin_email, generate_password_hash(admin_password)),
                    )


def authenticated_user():
    return session.get("user")


def require_roles(*roles):
    def decorator(view):
        @wraps(view)
        def wrapped(*args, **kwargs):
            user = authenticated_user()
            if not user:
                return jsonify({"error": "AUTHENTICATION_REQUIRED"}), 401
            if user.get("role") not in roles:
                return jsonify({"error": "FORBIDDEN"}), 403
            return view(*args, **kwargs)
        return wrapped
    return decorator


@app.before_request
def prepare_auth_schema():
    if request.path.startswith("/api/auth/"):
        try:
            ensure_auth_schema()
        except Exception:
            logging.exception("No fue posible preparar el esquema de autenticación")
            return jsonify({"error": "DATABASE_UNAVAILABLE"}), 503


@app.post("/api/auth/register")
def register():
    payload = request.get_json(silent=True) or {}
    name = str(payload.get("name", "")).strip()
    email = str(payload.get("email", "")).strip().lower()
    password = payload.get("password", "")
    if not name or len(name) > 120 or not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email):
        return jsonify({"error": "INVALID_ACCOUNT", "detail": "Revisa el nombre y el correo."}), 400
    if not isinstance(password, str) or len(password) < 8:
        return jsonify({"error": "INVALID_ACCOUNT", "detail": "La contraseña debe tener al menos 8 caracteres."}), 400
    try:
        with get_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """INSERT INTO users (email, name, phone, address, password_hash)
                       VALUES (%s, %s, %s, %s, %s)
                       RETURNING user_id, email, name, role""",
                    (email, name, payload.get("phone"), payload.get("address"), generate_password_hash(password)),
                )
                row = cursor.fetchone()
    except Exception as error:
        if "users_email_unique" in str(error) or "duplicate key" in str(error).lower():
            return jsonify({"error": "EMAIL_ALREADY_REGISTERED"}), 409
        logging.exception("Error al crear cuenta")
        return jsonify({"error": "DATABASE_UNAVAILABLE"}), 503
    user = {"user_id": row[0], "email": row[1], "name": row[2], "role": row[3]}
    session.clear()
    session["user"] = user
    return jsonify({"user": user}), 201


@app.post("/api/auth/login")
def login():
    payload = request.get_json(silent=True) or {}
    email = str(payload.get("email", "")).strip().lower()
    password = payload.get("password", "")
    requested_role = payload.get("requested_role")
    try:
        with get_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT user_id, email, name, role, password_hash, is_active FROM users WHERE lower(email) = %s",
                    (email,),
                )
                row = cursor.fetchone()
    except Exception:
        logging.exception("Error al iniciar sesión")
        return jsonify({"error": "DATABASE_UNAVAILABLE"}), 503
    if not row or not row[5] or not row[4] or not isinstance(password, str) or not check_password_hash(row[4], password):
        return jsonify({"error": "INVALID_CREDENTIALS", "detail": "Correo o contraseña incorrectos."}), 401
    user = {"user_id": row[0], "email": row[1], "name": row[2], "role": row[3]}
    if requested_role and requested_role != user["role"]:
        return jsonify({"error": "FORBIDDEN", "detail": "Esta cuenta no tiene acceso a esa interfaz."}), 403
    session.clear()
    session["user"] = user
    return jsonify({"user": user})


@app.get("/api/auth/me")
@require_roles("user", "admin")
def current_user():
    return jsonify({"user": authenticated_user()})


@app.post("/api/auth/logout")
def logout():
    session.clear()
    return jsonify({"status": "SIGNED_OUT"})

SERVICE_NAME = "orders"
ORDERS_TOPIC = "orders"

@app.get("/health")
def health():
    return jsonify({"service": "orders", "status": "UP"})


@app.get("/api/health")
def platform_health():
    """Respuesta inicial para que el frontend pueda comprobar la API."""
    return jsonify(
        {
            "status": "BASE_READY",
            "message": "La infraestructura funciona; el flujo aún debe implementarse.",
        }
    )


@app.get("/api/products")
def list_products():
    try:
        with get_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT product_id, name, product_description, price
                    FROM products
                    ORDER BY product_id
                    """
                )
                rows = cursor.fetchall()

    except Exception:
        logging.exception("Error al consultar el catálogo de productos")
        return jsonify({"error": "DATABASE_UNAVAILABLE"}), 503

    products = [
        {
            "product_id": product_id,
            "name": name,
            "description": description,
            "price": float(price),
        }
        for product_id, name, description, price in rows
    ]

    return jsonify(products)


@app.get("/api/inventory")
@require_roles("admin")
def list_inventory():
    try:
        with get_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute("""
                    SELECT p.product_id, p.name, p.product_description,
                           i.warehouse, i.quantity
                    FROM products p
                    LEFT JOIN inventory i USING (product_id)
                    ORDER BY p.product_id, i.warehouse
                """)
                rows = cursor.fetchall()
    except Exception:
        logging.exception("Error al consultar inventario")
        return jsonify({"error": "DATABASE_UNAVAILABLE"}), 503
    products = {}
    for product_id, name, description, warehouse, quantity in rows:
        product = products.setdefault(product_id, {
            "product_id": product_id, "name": name, "description": description,
            "stock": {"NORTE": 0, "SUR": 0}, "total": 0,
        })
        if warehouse:
            product["stock"][warehouse] = quantity
            product["total"] += quantity
    return jsonify({"products": list(products.values())})


@app.get("/api/orders")
@require_roles("admin")
def list_orders():
    try:
        with get_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT order_id, total, created_at, delivery_address, status
                    FROM orders
                    ORDER BY created_at DESC
                    """
                )
                rows = cursor.fetchall()

    except Exception:
        logging.exception("Error al consultar la lista de pedidos")
        return jsonify({"error": "DATABASE_UNAVAILABLE"}), 503

    orders = [
        {
            "order_id": order_id,
            "total": float(total),
            "created_at": created_at.isoformat(),
            "delivery_address": delivery_address,
            "status": status,
        }
        for order_id, total, created_at, delivery_address, status in rows
    ]

    return jsonify(orders)
    


@app.get("/api/orders/<order_id>")
@require_roles("user", "admin")
def get_order(order_id: str):
    try:
        with get_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT order_id, total, created_at, delivery_address, status, user_id
                    FROM orders
                    WHERE order_id = %s
                    """,
                    (order_id,),
                )

                order = cursor.fetchone()

                if order is None:
                    return jsonify(
                        {
                            "error": "ORDER_NOT_FOUND",
                            "order_id": order_id,
                        }
                    ), 404

                user = authenticated_user()
                if user["role"] != "admin" and order[5] != user["user_id"]:
                    return jsonify({"error": "FORBIDDEN"}), 403

                cursor.execute(
                    """
                    SELECT status, created_at
                    FROM order_history
                    WHERE order_id = %s
                    ORDER BY history_id
                    """,
                    (order_id,),
                )

                history_rows = cursor.fetchall()

                cursor.execute(
                    """
                    SELECT product_id, quantity
                    FROM order_items
                    WHERE order_id = %s
                    ORDER BY product_id
                    """,
                    (order_id,),
                )

                item_rows = cursor.fetchall()

    except Exception:
        logging.exception("Error al consultar el detalle del pedido")
        return jsonify({"error": "DATABASE_UNAVAILABLE"}), 503

    return jsonify(
        {
            "order_id": order[0],
            "total": float(order[1]),
            "created_at": order[2].isoformat(),
            "delivery_address": order[3],
            "status": order[4],
            "history": [
                {
                    "status": status,
                    "created_at": created_at.isoformat(),
                }
                for status, created_at in history_rows
            ],
            "items": [
                {
                    "product_id": product_id,
                    "quantity": quantity,
                }
                for product_id, quantity in item_rows
            ],
        }
    )

@app.patch("/api/orders/<order_id>/cancel")
@require_roles("user", "admin")
def cancel_order(order_id: str):
    try:
        with get_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT status, user_id
                    FROM orders
                    WHERE order_id = %s
                    FOR UPDATE
                    """,
                    (order_id,),
                )

                order = cursor.fetchone()

                if order is None:
                    return jsonify(
                        {
                            "error": "ORDER_NOT_FOUND",
                            "order_id": order_id,
                        }
                    ), 404

                current_status = order[0]
                user = authenticated_user()
                if user["role"] != "admin" and order[1] != user["user_id"]:
                    return jsonify({"error": "FORBIDDEN"}), 403

                if current_status != "RECEIVED":
                    return jsonify(
                        {
                            "error": "ORDER_CANNOT_BE_CANCELLED",
                            "order_id": order_id,
                            "status": current_status,
                        }
                    ), 409

                cursor.execute(
                    """
                    UPDATE orders
                    SET status = 'CANCELLED'
                    WHERE order_id = %s
                    """,
                    (order_id,),
                )

                cursor.execute(
                    """
                    INSERT INTO order_history (order_id, status)
                    VALUES (%s, %s)
                    """,
                    (order_id, "CANCELLED"),
                )

    except Exception:
        logging.exception("Error al cancelar el pedido")
        return jsonify({"error": "DATABASE_UNAVAILABLE"}), 503

    return jsonify(
        {
            "order_id": order_id,
            "status": "CANCELLED",
        }
    ), 200
   
def validate_order_payload(payload):
    if not isinstance(payload, dict):
        return "INVALID_JSON"

    delivery_address = payload.get("delivery_address")
    items = payload.get("items")

    if (
        not isinstance(delivery_address, str)
        or not delivery_address.strip()
        or len(delivery_address.strip()) > 200
    ):
        return "INVALID_DELIVERY_ADDRESS"

    if not isinstance(items, list) or not items:
        return "INVALID_ITEMS"

    product_ids = set()

    for item in items:
        if not isinstance(item, dict):
            return "INVALID_ITEM"

        product_id = item.get("product_id")
        quantity = item.get("quantity")

        if not isinstance(product_id, str) or not product_id.strip():
            return "INVALID_PRODUCT_ID"

        if (
            isinstance(quantity, bool)
            or not isinstance(quantity, int)
            or quantity <= 0
        ):
            return "INVALID_QUANTITY"

        normalized_product_id = product_id.strip()
        if normalized_product_id in product_ids:
            return "DUPLICATE_PRODUCT"

        product_ids.add(normalized_product_id)

    return None


@app.post("/api/orders")
@require_roles("user")
def create_order():
    payload = request.get_json(silent=True)
    validation_error = validate_order_payload(payload)

    if validation_error:
        return jsonify(
            {
                "error": "INVALID_ORDER",
                "detail": validation_error,
            }
        ), 400

    delivery_address = payload["delivery_address"].strip()
    items = [
        {
            "product_id": item["product_id"].strip(),
            "quantity": item["quantity"],
        }
        for item in payload["items"]
    ]


    try:
        with get_connection() as connection:
            with connection.cursor() as cursor:
                total = 0

                for item in items:
                    cursor.execute(
                        "SELECT price FROM products WHERE product_id = %s",
                        (item["product_id"],),
                    )
                    product = cursor.fetchone()

                    if product is None:
                        return jsonify(
                            {
                                "error": "INVALID_ORDER",
                                "detail": "PRODUCT_NOT_FOUND",
                                "product_id": item["product_id"],
                            }
                        ), 400

                    total += product[0] * item["quantity"]

                cursor.execute(
                    """
                    INSERT INTO orders (total, delivery_address, status, user_id)
                    VALUES (%s, %s, 'RECEIVED', %s)
                    RETURNING order_id
                    """,
                    (total, delivery_address, authenticated_user()["user_id"]),
                )

                order_id = cursor.fetchone()[0]

                for item in items:
                    cursor.execute(
                        """
                        INSERT INTO order_items (
                            order_id, product_id, quantity
                        )
                        VALUES (%s, %s, %s)
                        """,
                        (
                            order_id,
                            item["product_id"],
                            item["quantity"],
                        ),
                    )

                cursor.execute(
                    """
                    INSERT INTO order_history (order_id, status)
                    VALUES (%s, %s)
                    """,
                    (order_id, "RECEIVED"),
                )

    except Exception:
        logging.exception("Error al crear el pedido")
        return jsonify({"error": "DATABASE_UNAVAILABLE"}), 503
    try:
        event = build_event(
                "ORDER_CREATED",
                order_id,
                SERVICE_NAME,
                {"items": items},
        )

        producer = create_producer()
        publish(producer, ORDERS_TOPIC, event)

    except Exception:
        logging.exception("Error al publicar ORDER_CREATED")
        return jsonify(
            {
                "error": "KAFKA_UNAVAILABLE",
                "order_id": order_id,
            }
        ), 503

    return jsonify(
        {
            "order_id": order_id,
            "status": "RECEIVED",
            "total": float(total),
            "items": items,
        }
    ), 201


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "5001")))

