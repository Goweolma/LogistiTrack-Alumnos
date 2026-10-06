from datetime import datetime, timezone


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
                "ORD-001",
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
    assert data[0]["order_id"] == "ORD-001"
    assert data[0]["total"] == 150.50
    assert data[0]["status"] == "RECEIVED"


def test_get_order_includes_history_and_items(monkeypatch):
    cursor = FakeCursor(
        order=(
            "ORD-001",
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
    response = client.get("/api/orders/ORD-001")

    assert response.status_code == 200

    data = response.get_json()

    assert data["order_id"] == "ORD-001"

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
            "ORD-001",
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
    response = client.get("/api/orders/ORD-001")

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
    response = client.get("/api/orders/ORD-NOT-FOUND")

    assert response.status_code == 404

    assert response.get_json() == {
        "error": "ORDER_NOT_FOUND",
        "order_id": "ORD-NOT-FOUND",
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