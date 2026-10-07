"""Pruebas de Delivery.

DELIVERY_TEST_DATABASE_URL habilita la prueba PostgreSQL en un esquema temporal.
Kafka se simula; esta prueba no valida la integración con el broker.
"""
import json
import os
from pathlib import Path
import unittest
from uuid import uuid4
from unittest.mock import Mock, MagicMock, patch

import psycopg
from psycopg import sql

from common.events import build_event
from services.delivery.app import (
    app, decode_event, run_delivery, DeliveryStore, RetryLater,
    publish_confirmed, STAGES, EVENT_TYPES, FLEET,
)


@unittest.skipUnless(os.getenv("DELIVERY_TEST_DATABASE_URL"),
                     "Configura DELIVERY_TEST_DATABASE_URL para probar PostgreSQL")
class DeliveryPostgresTests(unittest.TestCase):
    def test_existing_schema_recovery_and_fleet_capacity(self):
        schema = "delivery_test_" + uuid4().hex
        init_sql = (Path(__file__).resolve().parents[1] /
                    "infrastructure/postgres/init.sql").read_text(encoding="utf-8")
        with psycopg.connect(os.environ["DELIVERY_TEST_DATABASE_URL"],
                             autocommit=True) as connection:
            # Todo, incluido el esquema temporal, se revierte incluso si falla la prueba.
            with connection.transaction(force_rollback=True):
                connection.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(schema)))
                connection.execute(sql.SQL("SET LOCAL search_path TO {}").format(sql.Identifier(schema)))
                connection.execute(init_sql)
                store = DeliveryStore(connection)
                store.initialize()
                store.initialize()  # Reiniciar el servicio no altera sus tablas.
                for number in range(1, 5):
                    connection.execute(
                        "INSERT INTO orders (order_id,total,delivery_address,status) "
                        "VALUES (%s,0,'Direccion de prueba','READY_FOR_DELIVERY')",
                        (f"PED-{number:06d}",))
                first = store.advance("PED-000001")
                second = store.advance("PED-000002")
                third = store.advance("PED-000003")
                self.assertEqual(len({event["payload"]["vehicle_id"]
                                      for event in (first, second, third)}), 3)
                with self.assertRaises(RetryLater):
                    store.advance("PED-000004")
                self.assertEqual(connection.execute(
                    "SELECT status FROM orders WHERE order_id='PED-000004'"
                ).fetchone()[0], "READY_FOR_DELIVERY")

                incoming = build_event("ORDER_READY", "PED-000001", "warehouse", {})
                with patch("services.delivery.app.publish_stage", side_effect=RetryLater):
                    with self.assertRaises(RetryLater):
                        run_delivery(store, Mock(), incoming, 0)
                self.assertFalse(store.processed(incoming["event_id"]))
                # Una nueva instancia recupera exactamente el evento persistido.
                restarted = DeliveryStore(connection)
                self.assertEqual(restarted.history("PED-000001"), [first])
                with patch("services.delivery.app.publish_stage") as publish:
                    run_delivery(restarted, Mock(), incoming, 0)
                    self.assertEqual([call.args[1]["payload"]["status"]
                                      for call in publish.call_args_list], list(STAGES))
                    self.assertEqual(publish.call_args_list[0].args[1], first)
                    publish.reset_mock()
                    run_delivery(restarted, Mock(), incoming, 0)
                    publish.assert_not_called()
                self.assertEqual(connection.execute(
                    "SELECT status FROM orders WHERE order_id='PED-000001'"
                ).fetchone()[0], "DELIVERED")
                self.assertEqual([row[0] for row in connection.execute(
                    "SELECT status FROM order_history WHERE order_id='PED-000001' ORDER BY history_id"
                ).fetchall()], list(STAGES))
                self.assertEqual(len(restarted.history("PED-000001")), 4)
                # La unidad entregada queda libre para el siguiente pedido.
                fourth = restarted.advance("PED-000004")
                self.assertEqual(fourth["payload"]["vehicle_id"], first["payload"]["vehicle_id"])


class DeliveryTests(unittest.TestCase):
    def test_initialize_only_creates_delivery_tables(self):
        connection = MagicMock()
        DeliveryStore(connection).initialize()
        statements = [call.args[0] for call in connection.execute.call_args_list]
        self.assertEqual(len(statements), 2)
        self.assertIn("CREATE TABLE IF NOT EXISTS delivery_assignments", statements[0])
        self.assertIn("CREATE TABLE IF NOT EXISTS delivery_events", statements[1])
        self.assertIn("UNIQUE (order_id, status)", statements[1])
        self.assertEqual(connection.transaction.call_count, 1)

    def test_assignment_and_events_use_own_tables(self):
        connection = MagicMock()
        connection.execute.return_value.fetchone.return_value = ("READY_FOR_DELIVERY", None, None)
        connection.execute.return_value.fetchall.return_value = []
        event = DeliveryStore(connection).advance("PED-000001")
        writes = {call.args[0]: call.args[1] for call in connection.execute.call_args_list
                  if call.args[0].startswith(("INSERT", "UPDATE"))}
        self.assertEqual(writes[
            "INSERT INTO delivery_assignments (order_id,driver_id,vehicle_id) VALUES (%s,%s,%s)"
        ], ("PED-000001", *FLEET[0]))
        self.assertEqual(writes["UPDATE orders SET status=%s WHERE order_id=%s"],
                         ("DRIVER_ASSIGNED", "PED-000001"))
        self.assertEqual(writes["INSERT INTO order_history (order_id,status) VALUES (%s,%s)"],
                         ("PED-000001", "DRIVER_ASSIGNED"))
        saved = writes[
            "INSERT INTO delivery_events (order_id,status,event_id,event) VALUES (%s,%s,%s,%s::jsonb)"
        ]
        self.assertEqual(json.loads(saved[3]), event)
        self.assertEqual(connection.transaction.call_count, 1)

    def test_history_recovers_original_events_in_stage_order(self):
        connection = MagicMock()
        events = [build_event(t, "PED-000001", "delivery", {"status": s})
                  for s, t in zip(STAGES, EVENT_TYPES)]
        connection.execute.return_value.fetchall.return_value = list(reversed(list(zip(STAGES, events))))
        self.assertEqual(DeliveryStore(connection).history("PED-000001"), events)
        self.assertIn("FROM delivery_events", connection.execute.call_args.args[0])

    def test_active_order_without_assignment_does_not_advance(self):
        connection = MagicMock()
        connection.execute.return_value.fetchone.return_value = ("IN_TRANSIT", None, None)
        with self.assertRaises(RetryLater):
            DeliveryStore(connection).advance("PED-000001")
        self.assertFalse(any(call.args[0].startswith(("UPDATE", "INSERT"))
                             for call in connection.execute.call_args_list))

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
