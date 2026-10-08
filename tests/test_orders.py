from datetime import datetime, timezone

import pytest
import services.orders.app as orders



NOW = datetime(2026, 10, 5, 12, 0, tzinfo=timezone.utc)


class FakeCursor:
    def __init__(self, order=None, history=None, items=None, orders_list=None):
        self.order = order
        self.history = history or []
        self.items = items or []
        self.orders_list = orders_list or []
        self.queries = []
        self.last_query = ""

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        return False

    def execute(self, query, params=None):
        self.last_query = " ".join(query.split())
        self.queries.append(self.last_query)

    def fetchone(self):
        return self.order

    def fetchall(self):
        if "FROM order_history" in self.last_query:
            return self.history

        if "FROM order_items" in self.last_query:
            return self.items

        return self.orders_list


class FakeConnection:
    def __init__(self, cursor):
        self.fake_cursor = cursor

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        return False

    def cursor(self):
        return self.fake_cursor


def test_list_orders(monkeypatch):
    cursor = FakeCursor(
        orders_list=[
            (
                "PED-000001",
                150.50,
                NOW,
                "Av. Universidad 100",
                "RECEIVED",
            )
        ]
    )

    monkeypatch.setattr(
        orders,
        "get_connection",
        lambda: FakeConnection(cursor),
    )

    client = orders.app.test_client()
    response = client.get("/api/orders")

    assert response.status_code == 200

    data = response.get_json()

    assert len(data) == 1
    assert data[0]["order_id"] == "PED-000001"
    assert data[0]["total"] == 150.50
    assert data[0]["status"] == "RECEIVED"


def test_get_order_includes_history_and_items(monkeypatch):
    cursor = FakeCursor(
        order=(
            "PED-000001",
            150.50,
            NOW,
            "Av. Universidad 100",
            "RECEIVED",
        ),
        history=[
            ("RECEIVED", NOW),
            ("PREPARING", NOW),
        ],
        items=[
            ("PROD-001", 2),
            ("PROD-002", 1),
        ],
    )

    monkeypatch.setattr(
        orders,
        "get_connection",
        lambda: FakeConnection(cursor),
    )

    client = orders.app.test_client()
    response = client.get("/api/orders/PED-000001")

    assert response.status_code == 200

    data = response.get_json()

    assert data["order_id"] == "PED-000001"

    assert data["history"] == [
        {
            "status": "RECEIVED",
            "created_at": NOW.isoformat(),
        },
        {
            "status": "PREPARING",
            "created_at": NOW.isoformat(),
        },
    ]

    assert data["items"] == [
        {
            "product_id": "PROD-001",
            "quantity": 2,
        },
        {
            "product_id": "PROD-002",
            "quantity": 1,
        },
    ]


def test_history_is_ordered_by_history_id(monkeypatch):
    cursor = FakeCursor(
        order=(
            "PED-000001",
            150.50,
            NOW,
            "Av. Universidad 100",
            "RECEIVED",
        )
    )

    monkeypatch.setattr(
        orders,
        "get_connection",
        lambda: FakeConnection(cursor),
    )

    client = orders.app.test_client()
    response = client.get("/api/orders/PED-000001")

    assert response.status_code == 200

    assert any(
        "ORDER BY history_id" in query
        for query in cursor.queries
    )


def test_get_order_returns_404(monkeypatch):
    cursor = FakeCursor(order=None)

    monkeypatch.setattr(
        orders,
        "get_connection",
        lambda: FakeConnection(cursor),
    )

    client = orders.app.test_client()
    response = client.get("/api/orders/PED-999999")

    assert response.status_code == 404

    assert response.get_json() == {
        "error": "ORDER_NOT_FOUND",
        "order_id": "PED-999999",
    }


def test_database_error_returns_503(monkeypatch):
    def broken_connection():
        raise RuntimeError("Database unavailable")

    monkeypatch.setattr(
        orders,
        "get_connection",
        broken_connection,
    )

    client = orders.app.test_client()
    response = client.get("/api/orders")

    assert response.status_code == 503
    assert response.get_json() == {
        "error": "DATABASE_UNAVAILABLE"
    }


def test_create_order_rejects_invalid_json():
    client = orders.app.test_client()

    response = client.post(
        "/api/orders",
        data="esto no es json",
        content_type="application/json",
    )

    assert response.status_code == 400
    assert response.get_json() == {
        "error": "INVALID_ORDER",
        "detail": "INVALID_JSON",
    }


@pytest.mark.parametrize(
    "payload, detail",
    [
        ({"delivery_address": "", "items": [{"product_id": "PROD-001", "quantity": 1}]},
         "INVALID_DELIVERY_ADDRESS"),
        ({"delivery_address": "A" * 201, "items": [{"product_id": "PROD-001", "quantity": 1}]},
         "INVALID_DELIVERY_ADDRESS"),
        ({"delivery_address": "Casa", "items": []}, "INVALID_ITEMS"),
        ({"delivery_address": "Casa", "items": [{"quantity": 1}]},
         "INVALID_PRODUCT_ID"),
        ({"delivery_address": "Casa", "items": [{"product_id": "PROD-001", "quantity": 0}]},
         "INVALID_QUANTITY"),
        ({"delivery_address": "Casa", "items": [{"product_id": "PROD-001", "quantity": -1}]},
         "INVALID_QUANTITY"),
        ({"delivery_address": "Casa", "items": [{"product_id": "PROD-001", "quantity": 1.5}]},
         "INVALID_QUANTITY"),
        ({"delivery_address": "Casa", "items": [{"product_id": "PROD-001", "quantity": "2"}]},
         "INVALID_QUANTITY"),
        ({"delivery_address": "Casa", "items": [{"product_id": "PROD-001", "quantity": True}]},
         "INVALID_QUANTITY"),
        ({"delivery_address": "Casa", "items": [
            {"product_id": "PROD-001", "quantity": 1},
            {"product_id": " PROD-001 ", "quantity": 2},
        ]}, "DUPLICATE_PRODUCT"),
    ],
)
def test_create_order_rejects_invalid_payload(payload, detail):
    client = orders.app.test_client()
    response = client.post("/api/orders", json=payload)

    assert response.status_code == 400
    assert response.get_json()["detail"] == detail


def test_create_order_returns_201_and_persists(monkeypatch):
    class CreateCursor:
        def __init__(self):
            self.current = None
            self.queries = []

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc_value, traceback):
            return False

        def execute(self, query, params=None):
            query = " ".join(query.split())
            self.queries.append((query, params))

            if "SELECT price FROM products" in query:
                prices = {
                    "PROD-001": (100,),
                    "PROD-002": (50,),
                }
                self.current = prices.get(params[0])
            elif "INSERT INTO orders" in query and "RETURNING order_id" in query:
                self.current = ("PED-000001",)

        def fetchone(self):
            return self.current

    cursor = CreateCursor()

    monkeypatch.setattr(
        orders,
        "get_connection",
        lambda: FakeConnection(cursor),
    )
    published = {}
    fake_producer = object()


    monkeypatch.setattr(
        orders,
        "create_producer",
        lambda: fake_producer,
    )

    def fake_publish(producer, topic, event):
        published["producer"] = producer
        published["topic"] = topic
        published["event"] = event

    monkeypatch.setattr(
        orders,
        "publish",
        fake_publish,
    )

    client = orders.app.test_client()
    response = client.post(
        "/api/orders",
        json={
            "delivery_address": "  Av. Universidad 100  ",
            "items": [
                {"product_id": " PROD-001 ", "quantity": 2},
                {"product_id": "PROD-002", "quantity": 1},
            ],
        },
    )

    assert response.status_code == 201

    data = response.get_json()
    assert data["order_id"] == "PED-000001"
    assert data["status"] == "RECEIVED"
    assert data["total"] == 250.0
    assert data["items"][0]["product_id"] == "PROD-001"


    assert published["producer"] is fake_producer
    assert published["topic"] == "orders"

    event = published["event"]

    assert event["event_type"] == "ORDER_CREATED"
    assert event["order_id"] == "PED-000001"
    assert event["source"] == "orders"
    assert event["payload"] == {
        "items": [
            {"product_id": "PROD-001", "quantity": 2},
            {"product_id": "PROD-002", "quantity": 1},
        ]
    }

    queries = [query for query, _ in cursor.queries]
    assert any("INSERT INTO orders" in query for query in queries)
    assert any("INSERT INTO order_items" in query for query in queries)
    assert any("INSERT INTO order_history" in query for query in queries)
    assert any("RETURNING order_id" in query for query in queries)

    order_insert = next(
        params for query, params in cursor.queries
        if "INSERT INTO orders" in query
    )
    assert order_insert[1] == "Av. Universidad 100"


def test_create_order_rejects_unknown_product(monkeypatch):
    cursor = FakeCursor(order=None)

    monkeypatch.setattr(
        orders,
        "get_connection",
        lambda: FakeConnection(cursor),
    )

    client = orders.app.test_client()
    response = client.post(
        "/api/orders",
        json={
            "delivery_address": "Casa",
            "items": [{"product_id": "PROD-999", "quantity": 1}],
        },
    )

    assert response.status_code == 400
    assert response.get_json()["detail"] == "PRODUCT_NOT_FOUND"

def test_create_order_returns_503_when_kafka_fails(monkeypatch):
    class CreateCursor:
        def __init__(self):
            self.current = None

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc_value, traceback):
            return False

        def execute(self, query, params=None):
            query = " ".join(query.split())

            if "SELECT price FROM products" in query:
                self.current = (100,)

            elif "INSERT INTO orders" in query and "RETURNING order_id" in query:
                self.current = ("PED-000001",)

        def fetchone(self):
            return self.current

    cursor = CreateCursor()

    monkeypatch.setattr(
        orders,
        "get_connection",
        lambda: FakeConnection(cursor),
    )

    monkeypatch.setattr(
        orders,
        "create_producer",
        lambda: object(),
    )

    def broken_publish(producer, topic, event):
        raise RuntimeError("Kafka unavailable")

    monkeypatch.setattr(
        orders,
        "publish",
        broken_publish,
    )

    client = orders.app.test_client()
    response = client.post(
        "/api/orders",
        json={
            "delivery_address": "Casa",
            "items": [
                {"product_id": "PROD-001", "quantity": 1},
            ],
        },
    )

    assert response.status_code == 503
    assert response.get_json() == {
        "error": "KAFKA_UNAVAILABLE",
        "order_id": "PED-000001",
    }

def test_create_order_rolls_back_when_persistence_fails(monkeypatch):
    class FailingCursor:
        def __init__(self):
            self.current = None

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc_value, traceback):
            return False

        def execute(self, query, params=None):
            query = " ".join(query.split())

            if "SELECT price FROM products" in query:
                self.current = (100,)

            elif "INSERT INTO orders" in query and "RETURNING order_id" in query:
                self.current = ("PED-000001",)

            elif "INSERT INTO order_items" in query:
                raise RuntimeError("Persistence failed")

        def fetchone(self):
            return self.current

    class RollbackConnection:
        def __init__(self, cursor):
            self.fake_cursor = cursor
            self.rolled_back = False

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc_value, traceback):
            if exc_type is not None:
                self.rolled_back = True
            return False

        def cursor(self):
            return self.fake_cursor

    cursor = FailingCursor()
    connection = RollbackConnection(cursor)

    monkeypatch.setattr(
        orders,
        "get_connection",
        lambda: connection,
    )

    client = orders.app.test_client()
    response = client.post(
        "/api/orders",
        json={
            "delivery_address": "Casa",
            "items": [
                {"product_id": "PROD-001", "quantity": 1},
            ],
        },
    )

    assert response.status_code == 503
    assert response.get_json() == {
        "error": "DATABASE_UNAVAILABLE"
    }
    assert connection.rolled_back is True


def test_list_products_returns_real_catalog(monkeypatch):
    cursor = FakeCursor(
        orders_list=[
            (
                "PROD-001",
                "Laptop empresarial",
                "Laptop de 14 pulgadas para uso corporativo",
                18999.00,
            ),
            (
                "PROD-002",
                "Monitor 24 pulgadas",
                "Monitor Full HD de 24 pulgadas",
                4299.00,
            ),
        ]
    )

    monkeypatch.setattr(
        orders,
        "get_connection",
        lambda: FakeConnection(cursor),
    )

    client = orders.app.test_client()
    response = client.get("/api/products")

    assert response.status_code == 200

    data = response.get_json()

    assert data == [
        {
            "product_id": "PROD-001",
            "name": "Laptop empresarial",
            "description": "Laptop de 14 pulgadas para uso corporativo",
            "price": 18999.0,
        },
        {
            "product_id": "PROD-002",
            "name": "Monitor 24 pulgadas",
            "description": "Monitor Full HD de 24 pulgadas",
            "price": 4299.0,
        },
    ]

    assert any(
        "FROM products" in query
        for query in cursor.queries
    )


def test_list_products_returns_503_when_database_fails(monkeypatch):
    def broken_connection():
        raise RuntimeError("Database unavailable")

    monkeypatch.setattr(
        orders,
        "get_connection",
        broken_connection,
    )

    client = orders.app.test_client()
    response = client.get("/api/products")

    assert response.status_code == 503
    assert response.get_json() == {
        "error": "DATABASE_UNAVAILABLE"
    }