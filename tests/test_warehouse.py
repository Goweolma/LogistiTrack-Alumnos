from common.events import build_event
import services.warehouse.app as warehouse
from unittest.mock import MagicMock
import pytest

def create_reserved_event():
    return build_event(
        "INVENTORY_RESERVED",
        "PED-000003",
        "inventory",
        {
            "warehouse": "NORTE",
            "items": [
                {
                    "quantity": 2,
                    "product_type": "frágil",
                }
            ],
        },
    )


def test_calculates_time_using_quantity_and_type(monkeypatch):
    monkeypatch.setenv("PREPARATION_DELAY_SECONDS", "2")

    seconds = warehouse.calculate_preparation_seconds(
        {
            "items": [
                {
                    "quantity": 2,
                    "product_type": "frágil",
                }
            ]
        }
    )

    assert seconds == 6.0


def test_ignores_inventory_rejected():
    event = build_event(
        "INVENTORY_REJECTED",
        "PED-000003",
        "inventory",
        {"reason": "OUT_OF_STOCK"},
    )

    result = warehouse.process_inventory_event(
        event,
        producer=object(),
    )

    assert result == "ignored"


def test_publishes_preparing_ready_and_order_ready(monkeypatch):
    event = create_reserved_event()
    published = []
    marked = []
    saved_statuses = []

    monkeypatch.setenv("PREPARATION_DELAY_SECONDS", "0")

    monkeypatch.setattr(
        warehouse,
        "event_was_processed",
        lambda event_id: False,
    )

    monkeypatch.setattr(
        warehouse,
        "publish",
        lambda producer, topic, outgoing_event: published.append(
            (topic, outgoing_event)
        ),
    )

    monkeypatch.setattr(
        warehouse,
        "mark_event_processed",
        lambda event_id: marked.append(event_id),
    )

    monkeypatch.setattr(
        warehouse,
        "save_order_status",
        lambda order_id, expected, new_status: saved_statuses.append(
            (order_id, expected, new_status)
        ),
    )

    result = warehouse.process_inventory_event(
        event,
        producer=object(),
    )

    assert result == "processed"

    assert [topic for topic, outgoing_event in published] == [
        "order-status",
        "order-status",
        "warehouse",
    ]

    assert [
        outgoing_event["event_type"]
        for topic, outgoing_event in published
    ] == [
        "PREPARING",
        "READY_FOR_DELIVERY",
        "ORDER_READY",
    ]

    assert marked == [
        event["event_id"]
    ]

    assert saved_statuses == [
        ("PED-000003", "INVENTORY_RESERVED", "PREPARING"),
        ("PED-000003", "PREPARING", "READY_FOR_DELIVERY"),
    ]


def test_does_not_process_duplicate_event(monkeypatch):
    event = create_reserved_event()
    published = []

    monkeypatch.setattr(
        warehouse,
        "event_was_processed",
        lambda event_id: True,
    )

    monkeypatch.setattr(
        warehouse,
        "publish",
        lambda producer, topic, outgoing_event: published.append(
            (topic, outgoing_event)
        ),
    )

    result = warehouse.process_inventory_event(
        event,
        producer=object(),
    )

    assert result == "duplicate"
    assert published == []

def test_negative_preparation_delay_becomes_zero(monkeypatch):
    monkeypatch.setenv("PREPARATION_DELAY_SECONDS", "-5")

    seconds = warehouse.calculate_preparation_seconds(
        {
            "items": [
                {
                    "quantity": 2,
                    "product_type": "normal",
                }
            ]
        }
    )

    assert seconds == 0.0

def fake_order_db(monkeypatch, current_status):
    connection = MagicMock()
    connection.__enter__.return_value = connection

    cursor = MagicMock()
    connection.cursor.return_value.__enter__.return_value = cursor
    cursor.fetchone.return_value = None if current_status is None else (current_status,)
    monkeypatch.setattr(warehouse, "get_connection", lambda: connection)
    return cursor


def test_save_order_status_updates_order_and_history(monkeypatch):
    cursor = fake_order_db(monkeypatch, "INVENTORY_RESERVED")

    result = warehouse.save_order_status(
        "PED-000003", "INVENTORY_RESERVED", "PREPARING"
    )

    assert result == "updated"
    cursor.execute.assert_any_call(
        "UPDATE orders SET status = %s WHERE order_id = %s",
        ("PREPARING", "PED-000003"),
    )
    cursor.execute.assert_any_call(
        "INSERT INTO order_history (order_id, status) VALUES (%s, %s)",
        ("PED-000003", "PREPARING"),
    )

def test_save_order_status_does_not_duplicate_history(monkeypatch):
    cursor = fake_order_db(monkeypatch, "PREPARING")

    result = warehouse.save_order_status(
        "PED-000003", "INVENTORY_RESERVED", "PREPARING"
    )

    assert result == "already"
    assert cursor.execute.call_count == 1


@pytest.mark.parametrize(
    ("current_status", "expected", "new_status"),
    [
        ("READY_FOR_DELIVERY", "INVENTORY_RESERVED", "PREPARING"),
        ("DELIVERED", "PREPARING", "READY_FOR_DELIVERY"),
    ],
)
def test_save_order_status_never_goes_back(
    monkeypatch, current_status, expected, new_status
):
    cursor = fake_order_db(monkeypatch, current_status)

    result = warehouse.save_order_status(
        "PED-000003", expected, new_status
    )

    assert result == "advanced"
    assert cursor.execute.call_count == 1


def test_save_order_status_fails_when_order_is_missing(monkeypatch):
    cursor = fake_order_db(monkeypatch, None)

    with pytest.raises(RuntimeError, match="No existe el pedido"):
        warehouse.save_order_status(
            "PED-000003", "INVENTORY_RESERVED", "PREPARING"
        )

    assert cursor.execute.call_count == 1


def test_save_order_status_requires_inventory_reservation(monkeypatch):
    cursor = fake_order_db(monkeypatch, "RECEIVED")

    with pytest.raises(RuntimeError, match="se esperaba INVENTORY_RESERVED"):
        warehouse.save_order_status(
            "PED-000003", "INVENTORY_RESERVED", "PREPARING"
        )

    assert cursor.execute.call_count == 1

def test_retry_reuses_event_ids_after_publish_failure(monkeypatch):
    event = create_reserved_event()
    published = []
    marked = []
    transitions = iter(("updated", "updated", "advanced", "already"))
    order_ready_attempts = 0

    monkeypatch.setenv("PREPARATION_DELAY_SECONDS", "0")
    monkeypatch.setattr(warehouse, "event_was_processed", lambda _id: False)
    monkeypatch.setattr(
        warehouse, "save_order_status", lambda *_args: next(transitions)
    )
    monkeypatch.setattr(warehouse, "mark_event_processed", marked.append)

    def fake_publish(_producer, _topic, outgoing):
        nonlocal order_ready_attempts
        published.append(outgoing)
        if outgoing["event_type"] == "ORDER_READY":
            order_ready_attempts += 1
            if order_ready_attempts == 1:
                raise RuntimeError("Kafka no confirmó")

    monkeypatch.setattr(warehouse, "publish", fake_publish)

    with pytest.raises(RuntimeError, match="Kafka no confirmó"):
        warehouse.process_inventory_event(event, object())

    assert marked == []
    assert warehouse.process_inventory_event(event, object()) == "processed"
    assert marked == [event["event_id"]]

    by_type = {
        kind: [item["event_id"] for item in published if item["event_type"] == kind]
        for kind in ("PREPARING", "READY_FOR_DELIVERY", "ORDER_READY")
    }
    assert len(by_type["PREPARING"]) == 1
    assert len(by_type["READY_FOR_DELIVERY"]) == 2
    assert len(by_type["ORDER_READY"]) == 2
    assert by_type["READY_FOR_DELIVERY"][0] == by_type["READY_FOR_DELIVERY"][1]
    assert by_type["ORDER_READY"][0] == by_type["ORDER_READY"][1]
    assert len({ids[0] for ids in by_type.values()}) == 3