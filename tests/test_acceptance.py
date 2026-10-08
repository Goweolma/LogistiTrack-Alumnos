"""La aceptación solo cierra cuando el historial llega a DELIVERED."""

from pathlib import Path

from scripts.acceptance_flow import EXPECTED_FLOW, classify_create, classify_flow, flow_statuses


ROOT = Path(__file__).resolve().parents[1]


def test_pending_create_is_blocked_and_not_a_created_order():
    assert classify_create(501, {"error": "NOT_IMPLEMENTED"}) == "blocked"
    assert classify_create(201, {"order_id": "PED-000001"}) == "created"
    assert classify_create(200, {"status": "RECEIVED"}) == "failed"
    assert classify_create(400, {"error": "INVALID_ORDER", "detail": "INVALID_ITEMS"}) == "failed"
    assert classify_create(501, {"error": "OTHER"}) == "failed"


def test_flow_accepts_only_the_complete_ordered_history():
    assert classify_flow(flow_statuses([{"status": status} for status in EXPECTED_FLOW])) == "complete"
    assert classify_flow(["RECEIVED", "INVENTORY_RESERVED"]) == "in_progress"
    assert classify_flow(["RECEIVED"]) == "in_progress"
    assert classify_flow(["RECEIVED", "INVENTORY_REJECTED"]) == "rejected"
    assert classify_flow(["RECEIVED", "DELIVERED"]) == "diverged"
    assert classify_flow([]) == "in_progress"
    assert classify_flow(None) == "invalid"
    assert flow_statuses([{"created_at": "ahora"}]) is None


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
