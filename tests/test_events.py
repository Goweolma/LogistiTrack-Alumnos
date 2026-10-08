import pytest

from common.events import build_event, validate_event


def test_build_event_contains_contract_fields():
    event = build_event("ORDER_CREATED", "PED-000001", "orders", {"quantity": 1})
    validate_event(event)
    assert event["event_type"] == "ORDER_CREATED"
    assert event["order_id"] == "PED-000001"
    assert event["event_id"]


def test_invalid_order_id_is_rejected_before_the_business_flow():
    event = build_event("ORDER_CREATED", "PED-000001", "orders", {"quantity": 1})
    event["order_id"] = "ORD-1"

    with pytest.raises(ValueError, match="PED-000000"):
        validate_event(event)
