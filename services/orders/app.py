import logging
import os
import re

from flask import Flask, jsonify, request
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from psycopg.errors import UniqueViolation
from werkzeug.security import check_password_hash, generate_password_hash

from common.database import get_connection
from common.events import build_event
from common.kafka_client import create_producer, publish


app = Flask(__name__)

SERVICE_NAME = "orders"
ORDERS_TOPIC = "orders"

AUTH_TOKEN_MAX_AGE_SECONDS = 8 * 60 * 60
AUTH_TOKEN_SECRET = os.getenv(
    "AUTH_TOKEN_SECRET",
    "logistitrack-development-auth-secret",
)

AUTH_SERIALIZER = URLSafeTimedSerializer(
    AUTH_TOKEN_SECRET,
    salt="orders-auth",
)


def create_auth_token(user_id):
    return AUTH_SERIALIZER.dumps(
        {
            "user_id": user_id,
        }
    )


def decode_auth_token(token):
    try:
        return AUTH_SERIALIZER.loads(
            token,
            max_age=AUTH_TOKEN_MAX_AGE_SECONDS,
        )
    except (BadSignature, SignatureExpired):
        return None


def get_bearer_token():
    authorization = request.headers.get("Authorization", "")

    if not authorization.startswith("Bearer "):
        return None

    token = authorization[7:].strip()
    return token or None

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

@app.post("/api/auth/register")
def register_user():
    payload = request.get_json(silent=True)

    if not isinstance(payload, dict):
        return jsonify(
            {
                "error": "INVALID_USER",
                "detail": "INVALID_JSON",
            }
        ), 400

    name = payload.get("name")
    email = payload.get("email")
    phone = payload.get("phone")
    address = payload.get("address")
    password = payload.get("password")

    if (
        not isinstance(name, str)
        or not name.strip()
        or len(name.strip()) > 120
    ):
        return jsonify(
            {
                "error": "INVALID_USER",
                "detail": "INVALID_NAME",
            }
        ), 400

    if (
        not isinstance(email, str)
        or len(email.strip()) > 254
        or re.fullmatch(
            r"[^@\s]+@[^@\s]+\.[^@\s]+",
            email.strip(),
        ) is None
    ):
        return jsonify(
            {
                "error": "INVALID_USER",
                "detail": "INVALID_EMAIL",
            }
        ), 400

    if (
        phone is not None
        and (
            not isinstance(phone, str)
            or re.fullmatch(r"\+?[0-9]{10,15}", phone.strip()) is None
        )
    ):
        return jsonify(
            {
                "error": "INVALID_USER",
                "detail": "INVALID_PHONE",
            }
        ), 400

    if (
        address is not None
        and (
            not isinstance(address, str)
            or len(address.strip()) > 200
        )
    ):
        return jsonify(
            {
                "error": "INVALID_USER",
                "detail": "INVALID_ADDRESS",
            }
        ), 400

    if not isinstance(password, str) or len(password) < 8:
        return jsonify(
            {
                "error": "INVALID_USER",
                "detail": "INVALID_PASSWORD",
            }
        ), 400

    normalized_email = email.strip().lower()
    normalized_name = name.strip()
    normalized_phone = phone.strip() if isinstance(phone, str) else None
    normalized_address = address.strip() if isinstance(address, str) else None
    password_hash = generate_password_hash(password)

    try:
        with get_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT user_id
                    FROM users
                    WHERE lower(email) = lower(%s)
                    """,
                    (normalized_email,),
                )

                if cursor.fetchone() is not None:
                    return jsonify(
                        {
                            "error": "USER_ALREADY_EXISTS",
                            "email": normalized_email,
                        }
                    ), 409

                cursor.execute(
                    """
                    INSERT INTO users (
                        email,
                        name,
                        phone,
                        address,
                        role,
                        password_hash
                    )
                    VALUES (%s, %s, %s, %s, 'user', %s)
                    RETURNING
                        user_id,
                        email,
                        name,
                        phone,
                        address,
                        role,
                        is_active
                    """,
                    (
                        normalized_email,
                        normalized_name,
                        normalized_phone,
                        normalized_address,
                        password_hash,
                    ),
                )

                user = cursor.fetchone()

    except UniqueViolation:
        logging.info(
            "Intento de registrar correo duplicado: %s",
            normalized_email,
        )
        return jsonify(
            {
                "error": "USER_ALREADY_EXISTS",
                "email": normalized_email,
            }
        ), 409

    except Exception:
        logging.exception("Error al registrar usuario")
        return jsonify({"error": "DATABASE_UNAVAILABLE"}), 503

    return jsonify(
        {
            "user": {
                "user_id": user[0],
                "email": user[1],
                "name": user[2],
                "phone": user[3],
                "address": user[4],
                "role": user[5],
                "is_active": user[6],
            }
        }
    ), 201

@app.post("/api/auth/login")
def login_user():
    payload = request.get_json(silent=True)

    if not isinstance(payload, dict):
        return jsonify(
            {
                "error": "INVALID_LOGIN",
                "detail": "INVALID_JSON",
            }
        ), 400

    email = payload.get("email")
    password = payload.get("password")
    requested_role = payload.get("requested_role")

    if not isinstance(email, str) or not email.strip():
        return jsonify(
            {
                "error": "INVALID_LOGIN",
                "detail": "INVALID_EMAIL",
            }
        ), 400

    if not isinstance(password, str) or not password:
        return jsonify(
            {
                "error": "INVALID_LOGIN",
                "detail": "INVALID_PASSWORD",
            }
        ), 400

    if requested_role not in ("user", "admin"):
        return jsonify(
            {
                "error": "INVALID_LOGIN",
                "detail": "INVALID_ROLE",
            }
        ), 400

    normalized_email = email.strip().lower()

    try:
        with get_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT
                        user_id,
                        email,
                        name,
                        phone,
                        address,
                        role,
                        is_active,
                        password_hash
                    FROM users
                    WHERE lower(email) = lower(%s)
                    """,
                    (normalized_email,),
                )

                user = cursor.fetchone()

    except Exception:
        logging.exception("Error al iniciar sesión")
        return jsonify({"error": "DATABASE_UNAVAILABLE"}), 503

    if user is None:
        return jsonify({"error": "INVALID_CREDENTIALS"}), 401

    if not check_password_hash(user[7], password):
        return jsonify({"error": "INVALID_CREDENTIALS"}), 401

    if not user[6]:
        return jsonify({"error": "ACCOUNT_INACTIVE"}), 403

    if user[5] != requested_role:
        return jsonify(
            {
                "error": "ROLE_ACCESS_DENIED",
                "requested_role": requested_role,
            }
        ), 403

    token = create_auth_token(user[0])

    return jsonify(
        {
            "token": token,
            "user": {
                "user_id": user[0],
                "email": user[1],
                "name": user[2],
                "phone": user[3],
                "address": user[4],
                "role": user[5],
                "is_active": user[6],
            },
        }
    ), 200


@app.get("/api/auth/session")
def get_auth_session():
    token = get_bearer_token()

    if token is None:
        return jsonify({"error": "AUTH_REQUIRED"}), 401

    session_data = decode_auth_token(token)

    if session_data is None:
        return jsonify({"error": "INVALID_SESSION"}), 401

    user_id = session_data.get("user_id")

    try:
        with get_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT
                        user_id,
                        email,
                        name,
                        phone,
                        address,
                        role,
                        is_active
                    FROM users
                    WHERE user_id = %s
                    """,
                    (user_id,),
                )

                user = cursor.fetchone()

    except Exception:
        logging.exception("Error al validar sesión")
        return jsonify({"error": "DATABASE_UNAVAILABLE"}), 503

    if user is None or not user[6]:
        return jsonify({"error": "INVALID_SESSION"}), 401

    return jsonify(
        {
            "user": {
                "user_id": user[0],
                "email": user[1],
                "name": user[2],
                "phone": user[3],
                "address": user[4],
                "role": user[5],
                "is_active": user[6],
            }
        }
    ), 200

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

@app.get("/api/package-sizes")
def list_package_sizes():
    try:
        with get_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT
                        package_size_id,
                        name,
                        length_cm,
                        width_cm,
                        height_cm,
                        max_weight_kg,
                        price,
                        is_active
                    FROM package_sizes
                    WHERE is_active = TRUE
                    ORDER BY price, package_size_id
                    """
                )
                rows = cursor.fetchall()

    except Exception:
        logging.exception("Error al consultar tamaños de paquete")
        return jsonify({"error": "DATABASE_UNAVAILABLE"}), 503

    package_sizes = [
        {
            "package_size_id": package_size_id,
            "name": name,
            "dimensions": {
                "length": float(length_cm),
                "width": float(width_cm),
                "height": float(height_cm),
                "unit": "cm",
            },
            "max_weight_kg": float(max_weight_kg),
            "price": float(price),
            "is_active": is_active,
        }
        for (
            package_size_id,
            name,
            length_cm,
            width_cm,
            height_cm,
            max_weight_kg,
            price,
            is_active,
        ) in rows
    ]

    return jsonify(package_sizes)

@app.get("/api/orders")
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
def get_order(order_id: str):
    try:
        with get_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT order_id, total, created_at, delivery_address, status
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
def cancel_order(order_id: str):
    try:
        with get_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT status
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
                    INSERT INTO orders (total, delivery_address, status)
                    VALUES (%s, %s, 'RECEIVED')
                    RETURNING order_id
                    """,
                    (total, delivery_address),
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

