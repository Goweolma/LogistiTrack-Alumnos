"""Pruebas unitarias de Delivery; no sustituyen la integración PostgreSQL/Kafka."""
import json
import unittest
from unittest.mock import Mock, MagicMock, patch

from common.events import build_event
from services.delivery.app import (
    app, decode_event, run_delivery, DeliveryStore, RetryLater,
    publish_confirmed, STAGES, EVENT_TYPES, FLEET,
)


class DeliveryTests(unittest.TestCase):
    def test_health(self):
        self.assertEqual(app.test_client().get("/health").json["status"], "UP")

    def test_contract(self):
        event = build_event("ORDER_READY", "PED-000001", "warehouse", {})
        self.assertEqual(decode_event(json.dumps(event)), event)
        for field, value in (("order_id", "bad"), ("event_id", "bad"),
                             ("payload", []), ("version", True), ("source", "")):
            with self.subTest(field=field), self.assertRaises(ValueError):
                decode_event(json.dumps({**event, field: value}))

    def test_flow_and_topics(self):
        store = Mock()
        store.processed.return_value = False
        store.history.return_value = []
        events = [build_event(t, "PED-000001", "delivery", {"status": s})
                  for s, t in zip(STAGES, EVENT_TYPES)]
        store.advance.side_effect = [*events, None]
        with patch("services.delivery.app.publish_confirmed") as publish:
            run_delivery(store, Mock(), {"event_id": "input", "order_id": "PED-000001"}, 0)
        self.assertEqual([c.args[1] for c in publish.call_args_list],
                         ["order-status", "order-status", "deliveries",
                          "order-status", "order-status", "deliveries"])
        store.finish.assert_called_once_with("input")

    def test_duplicate(self):
        store = Mock()
        store.processed.return_value = True
        run_delivery(store, Mock(), {"event_id": "input"}, 0)
        store.advance.assert_not_called()
        store.finish.assert_not_called()

    def test_assignment_skips_busy_unit(self):
        connection = MagicMock()
        connection.execute.return_value.fetchone.return_value = ("READY_FOR_DELIVERY", None, None)
        connection.execute.return_value.fetchall.return_value = [FLEET[0]]
        event = DeliveryStore(connection).advance("PED-000001")
        self.assertEqual(event["payload"]["vehicle_id"], "UNI-002")
        self.assertEqual(event["payload"]["driver_id"], "REP-002")
        self.assertEqual(connection.execute.call_args_list[0].args[0],
                         "SELECT pg_advisory_xact_lock(42004, 1)")

    def test_no_capacity_does_not_write(self):
        connection = MagicMock()
        connection.execute.return_value.fetchone.return_value = ("READY_FOR_DELIVERY", None, None)
        connection.execute.return_value.fetchall.return_value = list(FLEET)
        with self.assertRaises(RetryLater):
            DeliveryStore(connection).advance("PED-000001")
        self.assertFalse(any(c.args[0].startswith(("UPDATE", "INSERT"))
                             for c in connection.execute.call_args_list))

    def test_transitions_and_history(self):
        for previous, expected in zip(STAGES, STAGES[1:] + (None,)):
            with self.subTest(previous=previous):
                connection = MagicMock()
                connection.execute.return_value.fetchone.return_value = (previous, *FLEET[0])
                result = DeliveryStore(connection).advance("PED-000001")
                if expected is None:
                    self.assertIsNone(result)
                else:
                    self.assertEqual(result["payload"]["status"], expected)
                    writes = [c for c in connection.execute.call_args_list
                              if c.args[0].startswith("INSERT INTO order_history")]
                    self.assertEqual(len(writes), 1)

    def test_unready_order_does_not_advance(self):
        connection = MagicMock()
        connection.execute.return_value.fetchone.return_value = ("INVENTORY_REJECTED", None, None)
        with self.assertRaises(RetryLater):
            DeliveryStore(connection).advance("PED-000001")
        self.assertFalse(any(c.args[0].startswith("UPDATE")
                             for c in connection.execute.call_args_list))

    def test_recovery(self):
        store = Mock()
        store.processed.return_value = False
        saved = build_event("ORDER_DELIVERED", "PED-000001", "delivery", {"status": "DELIVERED"})
        store.history.return_value = [saved]
        store.advance.return_value = None
        incoming = {"event_id": "input", "order_id": "PED-000001"}
        with patch("services.delivery.app.publish_stage", side_effect=RetryLater):
            with self.assertRaises(RetryLater):
                run_delivery(store, Mock(), incoming, 0)
        store.finish.assert_not_called()
        with patch("services.delivery.app.publish_stage") as publish:
            run_delivery(store, Mock(), incoming, 0)
        self.assertIs(publish.call_args.args[1], saved)
        store.finish.assert_called_once()

    def test_unconfirmed_publish(self):
        producer = Mock()
        producer.flush.return_value = 1
        with self.assertRaises(RetryLater):
            publish_confirmed(producer, "order-status", {"order_id": "PED-000001"})


    def test_processed_events_uses_integrated_service_name(self):
        connection = MagicMock()
        store = DeliveryStore(connection)
        store.processed("input")
        self.assertIn("service_name=%s", connection.execute.call_args.args[0])
        self.assertEqual(connection.execute.call_args.args[1], ("input", "delivery"))
        store.finish("input")
        self.assertIn("(event_id,service_name)", connection.execute.call_args.args[0])
        self.assertEqual(connection.execute.call_args.args[1], ("input", "delivery"))

    def test_confirmed_publish(self):
        producer = Mock()
        producer.flush.return_value = 0
        producer.produce.side_effect = lambda *args, **kwargs: kwargs["on_delivery"](None, Mock())
        publish_confirmed(producer, "order-status", build_event("DRIVER_ASSIGNED", "PED-000001", "delivery", {}))

    def test_broker_rejection_does_not_finish(self):
        producer = Mock()
        producer.flush.return_value = 0
        producer.produce.side_effect = lambda *args, **kwargs: kwargs["on_delivery"]("broker failure", Mock())
        with self.assertRaises(RetryLater):
            publish_confirmed(producer, "order-status", build_event("DRIVER_ASSIGNED", "PED-000001", "delivery", {}))
