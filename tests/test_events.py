from common.events import build_event, validate_event


def test_build_event_contains_contract_fields():
    event = build_event("ORDER_CREATED", "PED-000001", "orders", {"quantity": 1})
    validate_event(event)
    assert event["event_type"] == "ORDER_CREATED"
    assert event["order_id"] == "PED-000001"
    assert event["event_id"]


def test_team_must_add_more_cases():
    # TODO(ALUMNO-7): sustituir esta prueba por errores de contrato y flujo final.
    assert True
