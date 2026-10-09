"""Contrato de Compose que debe seguir cumpliendo la infraestructura."""

from pathlib import Path


COMPOSE = Path(__file__).resolve().parents[1].joinpath("compose.yaml").read_text(encoding="utf-8")


def _service_block(name: str, following: str) -> str:
    return COMPOSE.split(f"\n  {name}:", 1)[1].split(f"\n  {following}:", 1)[0]


def test_ci_starts_the_platform_with_compose():
    workflow = Path(__file__).resolve().parents[1].joinpath(".github", "workflows", "tests.yml")
    text = workflow.read_text(encoding="utf-8")

    assert "docker compose config --quiet" in text
    assert "docker compose up -d --build" in text
    assert "python scripts/health_platform.py" in text
    assert "cp .env.example .env" in text


def test_credentials_come_from_the_environment():
    assert "logisti123" not in COMPOSE
    assert "${POSTGRES_PASSWORD:?" in COMPOSE
    assert "${DATABASE_URL:?" in COMPOSE
    assert "KAFKA_BOOTSTRAP_SERVERS: ${KAFKA_BOOTSTRAP_SERVERS:-kafka:9092}" in COMPOSE


def test_kafka_init_creates_the_six_topics_in_one_command():
    command = _service_block("kafka-init", "orders")

    assert 'entrypoint: ["/bin/bash", "-c"]' in command
    assert "command:\n      - >-" in command
    assert "set -e;" in command
    assert "--create --if-not-exists --topic $$topic" in command
    assert "for topic in orders inventory warehouse deliveries order-status dead-letter; do" in command
    assert command.count("healthcheck:") == 1
    assert "kafka:9092" in command


def test_services_meet_by_name_on_the_logistitrack_network():
    assert "name: logistitrack\n" in COMPOSE
    assert "PLAINTEXT://kafka:9092" in COMPOSE
    assert "--bootstrap-server kafka:9092" in COMPOSE
    assert "http://inventory:5002/health" in COMPOSE
    assert "http://warehouse:5003/health" in COMPOSE
    assert "http://delivery:5004/health" in COMPOSE
    assert "postgres_data:/var/lib/postgresql/data" in COMPOSE
    assert "/docker-entrypoint-initdb.d/01-init.sql:ro" in COMPOSE


def test_long_running_services_define_a_local_healthcheck():
    expected = {
        "postgres": "pg_isready",
        "kafka": "localhost:9092",
        "orders": "localhost:5001/health",
        "inventory": "localhost:5002/health",
        "warehouse": "localhost:5003/health",
        "delivery": "localhost:5004/health",
    }
    following = {
        "postgres": "kafka",
        "kafka": "kafka-init",
        "orders": "inventory",
        "inventory": "warehouse",
        "warehouse": "delivery",
        "delivery": "frontend",
    }

    for service, marker in expected.items():
        block = _service_block(service, following[service])
        assert block.count("healthcheck:") == 1
        assert marker in block

    frontend = COMPOSE.split("\n  frontend:", 1)[1].split("\nvolumes:", 1)[0]
    assert frontend.count("healthcheck:") == 1
    assert "127.0.0.1/frontend-health" in frontend
    assert "condition: service_healthy" in frontend
    assert frontend.count("condition: service_started") == 3
