import pytest

from common.events import build_event, validate_event


def test_validate_event_accepts_contract_event():
    validate_event(build_event("ORDER_CREATED", "PED-000001", "orders", {"quantity": 1}))


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("event_id", "not-a-uuid"),
        ("order_id", "ORDER-1"),
        ("timestamp", "2026-09-29T18:00:00"),
        ("version", 2),
        ("payload", []),
    ],
)
def test_validate_event_rejects_invalid_field(field, value):
    event = build_event("ORDER_CREATED", "PED-000001", "orders", {"quantity": 1})
    event[field] = value

    with pytest.raises(ValueError):
        validate_event(event)


def test_validate_event_rejects_unknown_fields():
    event = build_event("ORDER_CREATED", "PED-000001", "orders", {"quantity": 1})
    event["unexpected"] = True

    with pytest.raises(ValueError):
        validate_event(event)
