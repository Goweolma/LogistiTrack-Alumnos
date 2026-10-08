"""La interfaz llama al contrato real y explica las APIs que aún no existen."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
API = (ROOT / "frontend" / "js" / "api.js").read_text(encoding="utf-8")
APP = (ROOT / "frontend" / "js" / "app.js").read_text(encoding="utf-8")
HTML = (ROOT / "frontend" / "index.html").read_text(encoding="utf-8")


def test_client_uses_gateway_paths_and_pending_responses():
    for path in (
        "/api/health",
        "/api/products",
        "/api/orders",
        "/api/inventory",
        "/api/warehouse",
        "/api/delivery",
    ):
        assert path in API

    assert "/api/services/${service}/health" in API
    assert "status === 501" in API
    assert "NOT_IMPLEMENTED" in API
    assert "DATABASE_UNAVAILABLE" in API
    assert "ORDER_NOT_FOUND" in API


def test_screens_call_the_client_without_a_local_catalog():
    assert 'from "./api.js"' in APP
    assert 'type="module" src="/js/app.js"' in HTML
    assert "PROD-001" not in APP
    assert "Laptop empresarial" not in HTML

    for element_id in (
        "status",
        "services",
        "orderForm",
        "draftItems",
        "ordersBody",
        "search",
        "statusFilter",
        "trackingResult",
        "inventoryGrid",
    ):
        assert f'id="{element_id}"' in HTML

    assert "POST" in APP
    assert "describeApiError" in APP
    assert "PATHS.inventory" in APP
    assert "PATHS.products" in APP
    assert "PATHS.orders" in APP
