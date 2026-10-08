"""La prueba de aceptación no da por cerrado un alta que sigue en 501."""

from pathlib import Path

from scripts.acceptance_flow import classify_create


ROOT = Path(__file__).resolve().parents[1]


def test_pending_create_is_blocked_and_not_a_created_order():
    assert classify_create(501, {"error": "NOT_IMPLEMENTED"}) == "blocked"
    assert classify_create(201, {"order_id": "PED-000001"}) == "created"
    assert classify_create(200, {"status": "RECEIVED"}) == "failed"
    assert classify_create(400, {"error": "INVALID_ORDER", "detail": "INVALID_ITEMS"}) == "failed"
    assert classify_create(501, {"error": "OTHER"}) == "failed"


def test_manual_documents_the_visible_flow_and_the_pending_create():
    manual = (ROOT / "docs" / "MANUAL.md").read_text(encoding="utf-8")

    for marker in (
        "ORDER_CREATED",
        "INVENTORY_RESERVED",
        "ORDER_READY",
        "ORDER_DELIVERED",
        "PROCESSING_FAILED",
        "NOT_IMPLEMENTED",
        "python scripts/acceptance_flow.py",
        "/api/services/",
    ):
        assert marker in manual
