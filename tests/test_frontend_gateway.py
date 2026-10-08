"""El navegador llega a cada servicio por el proxy del frontend."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
NGINX = (ROOT / "frontend" / "nginx.conf").read_text(encoding="utf-8")
COMPOSE = (ROOT / "compose.yaml").read_text(encoding="utf-8")


def test_gateway_reserves_a_prefix_for_every_service():
    inventory = NGINX.index("location /api/inventory {")
    warehouse = NGINX.index("location /api/warehouse {")
    delivery = NGINX.index("location /api/delivery {")
    orders = NGINX.index("location /api/ {")

    assert inventory < orders
    assert warehouse < orders
    assert delivery < orders
    assert "inventory:5002" in NGINX
    assert "warehouse:5003" in NGINX
    assert "delivery:5004" in NGINX
    assert "orders:5001" in NGINX
    assert "proxy_pass http://$upstream$request_uri;" in NGINX


def test_gateway_exposes_same_origin_health_for_the_dashboard():
    for service, port in (
        ("orders", 5001),
        ("inventory", 5002),
        ("warehouse", 5003),
        ("delivery", 5004),
    ):
        assert f"location = /api/services/{service}/health" in NGINX
        assert f"{service}:{port}" in NGINX
        assert "proxy_pass http://$upstream/health;" in NGINX

    assert "resolver 127.0.0.11" in NGINX


def test_frontend_waits_until_the_proxied_services_exist():
    frontend = COMPOSE.split("\n  frontend:", 1)[1].split("\nvolumes:", 1)[0]

    assert "orders:" in frontend
    assert "condition: service_healthy" in frontend
    assert "inventory:" in frontend
    assert "warehouse:" in frontend
    assert "delivery:" in frontend
    assert frontend.count("condition: service_started") == 3
