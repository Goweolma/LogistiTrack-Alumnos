from common.events import build_event
import services.warehouse.app as warehouse


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
        lambda event_id, order_id: marked.append(
            (event_id, order_id)
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
        (event["event_id"], event["order_id"])
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