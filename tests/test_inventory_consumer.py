import json

import pytest
from confluent_kafka import Producer

from common.events import build_event, validate_event
import services.inventory.app as inventory


class FakeDatabase:
    """Simula las tablas que usa Inventory: inventory, orders, order_history, processed_events e inventory_reservations."""

    def __init__(self, stock, orders):
        self.stock = dict(stock)
        self.orders = dict(orders)
        self.history = []
        self.processed = set()
        self.reservations = {}
        self.queries = []
        self.commits = 0
        self.rollbacks = 0


class FakeCursor:
    def __init__(self, db, pending):
        self.db = db
        self.pending = pending
        self.rowcount = 0
        self.result = []

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        return False

    def execute(self, query, params=()):
        query = " ".join(query.split())
        self.db.queries.append(query)

        if query.startswith("INSERT INTO processed_events"):
            key = tuple(params)
            duplicate = key in self.db.processed or key in self.pending["processed"]
            self.rowcount = 0 if duplicate else 1
            if not duplicate:
                self.pending["processed"].add(key)
        elif query.startswith("SELECT result_event"):
            reservation = self.db.reservations.get(params[0])
            self.result = [(reservation["result_event"],)] if reservation else []
        elif query.startswith("SELECT status FROM orders"):
            assert query.endswith("FOR UPDATE")
            status = self.pending["orders"].get(params[0])
            self.result = [(status,)] if status else []
        elif query.startswith("UPDATE orders SET status"):
            status, order_id = params
            self.pending["orders"][order_id] = status
            self.rowcount = 1
        elif query.startswith("INSERT INTO order_history"):
            self.pending["history"].append(tuple(params))
        elif query.startswith("SELECT product_id, warehouse, quantity"):
            products = params[0]
            self.result = sorted(
                (pid, warehouse, quantity)
                for (pid, warehouse), quantity in self.pending["stock"].items()
                if pid in products
            )
        elif query.startswith("UPDATE inventory"):
            quantity, pid, warehouse = params
            new_quantity = self.pending["stock"][(pid, warehouse)] - quantity
            if new_quantity < 0:
                raise RuntimeError("CHECK (quantity >= 0) violado")
            self.pending["stock"][(pid, warehouse)] = new_quantity
            self.rowcount = 1
        elif query.startswith("INSERT INTO inventory_reservations"):
            event_id, order_id, status, warehouse, result_event = params
            self.pending["reservations"][event_id] = {
                "order_id": order_id,
                "status": status,
                "warehouse": warehouse,
                "result_event": json.loads(result_event),
            }
        else:
            raise AssertionError(f"Consulta inesperada: {query}")

    def fetchone(self):
        return self.result[0] if self.result else None

    def fetchall(self):
        return self.result


class FakeConnection:
    """Aplica los cambios solo al salir sin error, igual que psycopg con `with`."""

    def __init__(self, db):
        self.db = db
        self.pending = {
            "stock": dict(db.stock),
            "orders": dict(db.orders),
            "history": [],
            "processed": set(),
            "reservations": {},
        }

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        if exc_type is None:
            self.db.stock = self.pending["stock"]
            self.db.orders = self.pending["orders"]
            self.db.history.extend(self.pending["history"])
            self.db.processed |= self.pending["processed"]
            self.db.reservations.update(self.pending["reservations"])
            self.db.commits += 1
        else:
            self.db.rollbacks += 1
        return False

    def cursor(self):
        return FakeCursor(self.db, self.pending)


@pytest.fixture
def db(monkeypatch):
    database = FakeDatabase(
        {
            ("PROD-001", "NORTE"): 2,
            ("PROD-001", "SUR"): 5,
            ("PROD-002", "NORTE"): 10,
            ("PROD-002", "SUR"): 0,
        },
        orders={"PED-000001": "RECEIVED"},
    )
    monkeypatch.setattr(inventory, "get_connection", lambda: FakeConnection(database))
    return database


@pytest.fixture
def published(monkeypatch):
    messages = []
    monkeypatch.setattr(
        inventory,
        "publish_confirmed",
        lambda producer, topic, event: messages.append((topic, event)),
    )
    return messages


def order_created(*items):
    return build_event(
        "ORDER_CREATED",
        "PED-000001",
        "orders",
        {"items": [{"product_id": pid, "quantity": quantity} for pid, quantity in items]},
    )


def test_reserves_in_norte_and_publishes_result(db, published):
    event = order_created(("PROD-001", 2), ("PROD-002", 3))

    result = inventory.process_order_event(event, producer=object())

    assert result == "reserved"
    assert db.stock[("PROD-001", "NORTE")] == 0
    assert db.stock[("PROD-002", "NORTE")] == 7
    assert db.stock[("PROD-001", "SUR")] == 5

    assert [topic for topic, _ in published] == ["inventory", "order-status"]
    reserved = published[0][1]
    validate_event(reserved)
    assert reserved["event_type"] == "INVENTORY_RESERVED"
    assert reserved["source"] == "inventory"
    assert reserved["order_id"] == "PED-000001"
    assert reserved["payload"]["warehouse"] == "NORTE"
    assert reserved["payload"]["items"] == event["payload"]["items"]
    assert reserved["payload"]["order_event_id"] == event["event_id"]
    assert published[1][1] == reserved


def test_uses_sur_when_norte_cannot_fulfil_the_whole_order(db, published):
    result = inventory.process_order_event(order_created(("PROD-001", 4)), producer=object())

    assert result == "reserved"
    assert published[0][1]["payload"]["warehouse"] == "SUR"
    assert db.stock[("PROD-001", "SUR")] == 1
    assert db.stock[("PROD-001", "NORTE")] == 2


def test_rejects_without_touching_stock_when_no_warehouse_has_enough(db, published):
    before = dict(db.stock)

    result = inventory.process_order_event(order_created(("PROD-001", 6)), producer=object())

    assert result == "rejected"
    assert db.stock == before
    assert not any(query.startswith("UPDATE inventory") for query in db.queries)
    rejected = published[0][1]
    validate_event(rejected)
    assert rejected["event_type"] == "INVENTORY_REJECTED"
    assert rejected["payload"]["reason"] == "OUT_OF_STOCK"
    assert "warehouse" not in rejected["payload"]


def test_rejects_unknown_product(db, published):
    result = inventory.process_order_event(order_created(("PROD-999", 1)), producer=object())

    assert result == "rejected"
    assert published[0][1]["event_type"] == "INVENTORY_REJECTED"


def test_repeated_items_are_added_before_checking_stock(db, published):
    result = inventory.process_order_event(
        order_created(("PROD-001", 2), ("PROD-001", 2)),
        producer=object(),
    )

    assert result == "reserved"
    assert published[0][1]["payload"]["warehouse"] == "SUR"
    assert db.stock[("PROD-001", "SUR")] == 1


def test_duplicate_event_does_not_reserve_twice_and_republishes_same_result(db, published):
    event = order_created(("PROD-001", 1))

    first = inventory.process_order_event(event, producer=object())
    second = inventory.process_order_event(event, producer=object())

    assert (first, second) == ("reserved", "duplicate")
    assert db.stock[("PROD-001", "SUR")] == 4
    assert len(db.reservations) == 1
    assert [topic for topic, _ in published] == ["inventory", "order-status", "inventory", "order-status"]
    assert published[2][1] == published[0][1]


def test_locks_rows_inside_the_transaction(db, published):
    inventory.process_order_event(order_created(("PROD-001", 1)), producer=object())

    lock_query = next(query for query in db.queries if query.startswith("SELECT product_id"))
    assert "FOR UPDATE" in lock_query
    assert db.queries[0].startswith("INSERT INTO processed_events")
    assert db.commits == 1


def test_failed_transaction_rolls_back_and_publishes_nothing(db, published, monkeypatch):
    def broken_choice(stock, quantities):
        raise RuntimeError("fallo a mitad de la transacción")

    monkeypatch.setattr(inventory, "choose_warehouse", broken_choice)
    event = order_created(("PROD-001", 1))

    with pytest.raises(RuntimeError):
        inventory.process_order_event(event, producer=object())

    assert db.rollbacks == 1
    assert db.processed == set()
    assert published == []


def test_ignores_events_other_than_order_created(db, published):
    event = build_event("ORDER_CANCELLED", "PED-000001", "orders", {})

    assert inventory.process_order_event(event, producer=object()) == "ignored"
    assert published == []
    assert db.queries == []


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"items": []},
        {"items": [{"quantity": 1}]},
        {"items": [{"product_id": "PROD-001", "quantity": 0}]},
        {"items": [{"product_id": "PROD-001", "quantity": -3}]},
        {"items": [{"product_id": "PROD-001", "quantity": "2"}]},
        {"items": [{"product_id": "PROD-001", "quantity": True}]},
    ],
)
def test_invalid_payload_raises_value_error_before_touching_database(db, published, payload):
    event = build_event("ORDER_CREATED", "PED-000001", "orders", payload)

    with pytest.raises(ValueError):
        inventory.process_order_event(event, producer=object())

    assert db.queries == []
    assert published == []


@pytest.mark.parametrize(
    ("stock", "quantities", "expected"),
    [
        # Ambos surten el pedido: gana el que tiene más existencias.
        ({("PROD-001", "NORTE"): 3, ("PROD-001", "SUR"): 9}, {"PROD-001": 3}, "SUR"),
        ({("PROD-001", "NORTE"): 9, ("PROD-001", "SUR"): 3}, {"PROD-001": 3}, "NORTE"),
        # Empate: se conserva NORTE.
        ({("PROD-001", "NORTE"): 5, ("PROD-001", "SUR"): 5}, {"PROD-001": 2}, "NORTE"),
        # Varios productos: se suma la disponibilidad de todos los productos pedidos.
        (
            {
                ("PROD-001", "NORTE"): 5,
                ("PROD-002", "NORTE"): 1,
                ("PROD-001", "SUR"): 2,
                ("PROD-002", "SUR"): 2,
            },
            {"PROD-001": 1, "PROD-002": 1},
            "NORTE",
        ),
        # Más existencias no basta: el almacén debe surtir el pedido completo.
        (
            {
                ("PROD-001", "NORTE"): 100,
                ("PROD-002", "NORTE"): 0,
                ("PROD-001", "SUR"): 1,
                ("PROD-002", "SUR"): 1,
            },
            {"PROD-001": 1, "PROD-002": 1},
            "SUR",
        ),
        # Solo uno alcanza.
        ({("PROD-001", "NORTE"): 3, ("PROD-001", "SUR"): 9}, {"PROD-001": 4}, "SUR"),
        # Ninguno alcanza.
        ({("PROD-001", "NORTE"): 3, ("PROD-001", "SUR"): 9}, {"PROD-001": 10}, None),
    ],
)
def test_choose_warehouse_picks_the_one_with_more_availability(stock, quantities, expected):
    assert inventory.choose_warehouse(stock, quantities) == expected


def test_reserves_in_the_warehouse_with_more_availability(db, published):
    # PROD-001: NORTE tiene 2 y SUR tiene 5; ambos surten 1 unidad, pero SUR tiene más.
    result = inventory.process_order_event(order_created(("PROD-001", 1)), producer=object())

    assert result == "reserved"
    assert published[0][1]["payload"]["warehouse"] == "SUR"
    assert db.stock[("PROD-001", "SUR")] == 4
    assert db.stock[("PROD-001", "NORTE")] == 2
    assert db.reservations[next(iter(db.reservations))]["warehouse"] == "SUR"


class FakeMessage:
    def __init__(self, value):
        self._value = value

    def error(self):
        return None

    def value(self):
        return self._value


class StopConsumer(Exception):
    pass


class FakeConsumer:
    def __init__(self, messages):
        self.messages = list(messages)
        self.committed = []

    def poll(self, timeout):
        if not self.messages:
            raise StopConsumer
        return self.messages.pop(0)

    def commit(self, message, asynchronous):
        self.committed.append(message)

    def close(self):
        pass


def run_consumer_once(monkeypatch, consumer):
    monkeypatch.setattr(inventory, "create_producer", lambda: object())
    monkeypatch.setattr(inventory, "create_consumer", lambda group, topics: consumer)

    def stop(seconds):
        raise StopConsumer

    monkeypatch.setattr(inventory.time, "sleep", stop)
    with pytest.raises(StopConsumer):
        inventory.consume_orders()


def test_consumer_sends_invalid_message_to_dead_letter_and_commits(monkeypatch, db, published):
    dead_letters = []
    monkeypatch.setattr(
        inventory,
        "publish_dead_letter",
        lambda producer, event, reason, source: dead_letters.append((event, source)),
    )
    valid = FakeMessage(json.dumps(order_created(("PROD-001", 1))).encode())
    invalid = FakeMessage(b"no es json")
    consumer = FakeConsumer([invalid, valid])

    run_consumer_once(monkeypatch, consumer)

    assert dead_letters == [({"raw_message": "no es json"}, "inventory")]
    assert consumer.committed == [invalid, valid]
    assert published[0][1]["event_type"] == "INVENTORY_RESERVED"


def test_consumer_does_not_commit_offset_when_database_fails(monkeypatch, published):
    def broken_connection():
        raise RuntimeError("Database unavailable")

    monkeypatch.setattr(inventory, "get_connection", broken_connection)
    message = FakeMessage(json.dumps(order_created(("PROD-001", 1))).encode())
    consumer = FakeConsumer([message])

    run_consumer_once(monkeypatch, consumer)

    assert consumer.committed == []
    assert published == []


def count_queries(db, prefix):
    return sum(query.startswith(prefix) for query in db.queries)


def test_reservation_updates_order_status_and_history(db, published):
    inventory.process_order_event(order_created(("PROD-001", 1)), producer=object())

    assert db.orders["PED-000001"] == "INVENTORY_RESERVED"
    assert db.history == [("PED-000001", "INVENTORY_RESERVED")]


def test_rejection_updates_order_status_and_history(db, published):
    inventory.process_order_event(order_created(("PROD-001", 99)), producer=object())

    assert db.orders["PED-000001"] == "INVENTORY_REJECTED"
    assert db.history == [("PED-000001", "INVENTORY_REJECTED")]


def test_duplicate_does_not_update_order_or_insert_history_again(db, published):
    event = order_created(("PROD-001", 1))

    inventory.process_order_event(event, producer=object())
    inventory.process_order_event(event, producer=object())

    assert db.history == [("PED-000001", "INVENTORY_RESERVED")]
    assert count_queries(db, "UPDATE orders") == 1
    assert count_queries(db, "INSERT INTO order_history") == 1


def test_order_status_and_history_roll_back_with_the_reservation(db, published, monkeypatch):
    def broken_build_event(*args):
        raise RuntimeError("fallo después de escribir historial")

    monkeypatch.setattr(inventory, "build_event", broken_build_event)

    with pytest.raises(RuntimeError):
        inventory.process_order_event(order_created(("PROD-001", 1)), producer=object())

    assert count_queries(db, "INSERT INTO order_history") == 1
    assert db.orders["PED-000001"] == "RECEIVED"
    assert db.history == []
    assert db.stock[("PROD-001", "NORTE")] == 2
    assert db.processed == set()


def test_missing_order_rolls_back_and_raises_value_error(db, published):
    event = build_event(
        "ORDER_CREATED",
        "PED-000777",
        "orders",
        {"items": [{"product_id": "PROD-001", "quantity": 1}]},
    )
    before = dict(db.stock)

    with pytest.raises(ValueError, match="ORDER_NOT_FOUND"):
        inventory.process_order_event(event, producer=object())

    assert db.stock == before
    assert db.processed == set()
    assert db.history == []
    assert published == []


class FakeKafkaProducer:
    """Imita confluent_kafka.Producer: el callback de entrega se ejecuta durante flush()."""

    def __init__(self, error=None, deliver=True):
        self.error = error
        self.deliver = deliver
        self.queue = []
        self.messages = []

    def produce(self, topic, value, on_delivery):
        self.queue.append((topic, value, on_delivery))

    def flush(self, timeout):
        if not self.deliver:
            return len(self.queue)
        for topic, value, on_delivery in self.queue:
            if self.error is None:
                self.messages.append((topic, json.loads(value)))
            on_delivery(self.error, None)
        self.queue = []
        return 0


def result_event():
    return build_event("INVENTORY_RESERVED", "PED-000001", "inventory", {"warehouse": "NORTE"})


def unreachable_kafka_producer():
    # Producer real de librdkafka sin broker disponible: la entrega falla por tiempo de espera.
    return Producer({"bootstrap.servers": "127.0.0.1:1", "message.timeout.ms": 1000, "log_level": 0})


def test_publish_confirmed_sends_when_broker_confirms():
    producer = FakeKafkaProducer()
    event = result_event()

    inventory.publish_confirmed(producer, "inventory", event)

    assert producer.messages == [("inventory", event)]


@pytest.mark.parametrize(
    "producer",
    [FakeKafkaProducer(error="KafkaError{BROKER_NOT_AVAILABLE}"), FakeKafkaProducer(deliver=False)],
    ids=["delivery-error", "flush-timeout"],
)
def test_publish_confirmed_raises_when_delivery_is_not_confirmed(producer):
    with pytest.raises(inventory.PublishError):
        inventory.publish_confirmed(producer, "inventory", result_event())


def test_publish_confirmed_raises_on_real_kafka_failure():
    with pytest.raises(inventory.PublishError):
        inventory.publish_confirmed(unreachable_kafka_producer(), "inventory", result_event())


def test_real_publish_failure_skips_offset_commit_and_retry_republishes_stored_result(monkeypatch, db):
    message = FakeMessage(json.dumps(order_created(("PROD-001", 1))).encode())
    first_attempt = FakeConsumer([message])
    redelivery = FakeConsumer([message])
    consumers = [first_attempt, redelivery]
    working_producer = FakeKafkaProducer()
    producers = [unreachable_kafka_producer(), working_producer]

    monkeypatch.setattr(inventory, "create_producer", lambda: producers.pop(0))
    monkeypatch.setattr(inventory, "create_consumer", lambda group, topics: consumers.pop(0))

    def sleep(seconds):
        if not consumers:
            raise StopConsumer

    monkeypatch.setattr(inventory.time, "sleep", sleep)

    with pytest.raises(StopConsumer):
        inventory.consume_orders()

    assert first_attempt.committed == []
    assert redelivery.committed == [message]

    stored = next(iter(db.reservations.values()))["result_event"]
    assert working_producer.messages == [("inventory", stored), ("order-status", stored)]
    assert db.stock[("PROD-001", "SUR")] == 4
    assert db.history == [("PED-000001", "INVENTORY_RESERVED")]


def test_second_order_created_with_new_event_id_does_not_reserve_again(db, published):
    first = order_created(("PROD-001", 1))
    second = order_created(("PROD-001", 1))
    inventory.process_order_event(first, producer=object())

    with pytest.raises(ValueError, match="INVALID_ORDER_STATE"):
        inventory.process_order_event(second, producer=object())

    assert db.stock[("PROD-001", "SUR")] == 4
    assert db.orders["PED-000001"] == "INVENTORY_RESERVED"
    assert db.history == [("PED-000001", "INVENTORY_RESERVED")]
    assert db.processed == {(first["event_id"], "inventory")}
    assert len(published) == 2


@pytest.mark.parametrize("status", ["INVENTORY_RESERVED", "INVENTORY_REJECTED", "PREPARING", "DELIVERED"])
def test_order_not_in_received_is_not_reserved_nor_moved_back(db, published, status):
    db.orders["PED-000001"] = status
    before = dict(db.stock)

    with pytest.raises(ValueError, match=f"INVALID_ORDER_STATE: se esperaba RECEIVED, pero está en {status}"):
        inventory.process_order_event(order_created(("PROD-001", 1)), producer=object())

    assert db.orders["PED-000001"] == status
    assert db.stock == before
    assert db.history == []
    assert db.processed == set()
    assert published == []


def test_redelivered_event_is_still_a_duplicate_after_the_order_advances(db, published):
    event = order_created(("PROD-001", 1))
    inventory.process_order_event(event, producer=object())
    db.orders["PED-000001"] = "DELIVERED"

    assert inventory.process_order_event(event, producer=object()) == "duplicate"

    assert db.orders["PED-000001"] == "DELIVERED"
    assert db.history == [("PED-000001", "INVENTORY_RESERVED")]
    assert published[2][1] == published[0][1]


def test_consumer_sends_invalid_order_state_to_dead_letter_and_commits(monkeypatch, db, published):
    db.orders["PED-000001"] = "DELIVERED"
    dead_letters = []
    monkeypatch.setattr(
        inventory,
        "publish_dead_letter",
        lambda producer, event, reason, source: dead_letters.append(reason),
    )
    message = FakeMessage(json.dumps(order_created(("PROD-001", 1))).encode())
    consumer = FakeConsumer([message])

    run_consumer_once(monkeypatch, consumer)

    assert len(dead_letters) == 1 and dead_letters[0].startswith("INVALID_ORDER_STATE")
    assert consumer.committed == [message]
    assert db.stock[("PROD-001", "NORTE")] == 2
