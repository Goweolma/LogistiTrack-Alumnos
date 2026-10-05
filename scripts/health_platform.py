"""Valida la salud completa de la plataforma LogistiTrack.

Comprueba el estado de los contenedores, sus healthchecks, los endpoints HTTP
y la existencia de los seis topics de Kafka.
"""

from __future__ import annotations

import json
import subprocess
from collections.abc import Iterable
from urllib.error import URLError
from urllib.request import urlopen


EXPECTED_SERVICES = {
    "postgres",
    "kafka",
    "kafka-init",
    "orders",
    "inventory",
    "warehouse",
    "delivery",
    "frontend",
}
EXPECTED_TOPICS = {
    "orders",
    "inventory",
    "warehouse",
    "deliveries",
    "order-status",
    "dead-letter",
}
HTTP_HEALTHCHECKS = {
    "frontend": "http://localhost:8080/frontend-health",
    "orders": "http://localhost:5001/health",
    "inventory": "http://localhost:5002/health",
    "warehouse": "http://localhost:5003/health",
    "delivery": "http://localhost:5004/health",
}
HEALTHY_SERVICES = {"postgres", "kafka", "orders"}


def run_command(args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(args, capture_output=True, text=True, check=False)


def parse_compose_records(output: str) -> list[dict]:
    """Parsea la salida JSON por línea de `docker compose ps`."""
    records = []
    for line in output.splitlines():
        line = line.strip()
        if line:
            records.append(json.loads(line))
    return records


def report(ok: bool, message: str) -> bool:
    print(f"[{'OK' if ok else 'ERROR'}] {message}")
    return ok


def check_containers() -> bool:
    result = run_command(["docker", "compose", "ps", "--all", "--format", "json"])
    if result.returncode != 0:
        return report(False, f"docker compose ps: {result.stderr.strip()}")

    try:
        records = parse_compose_records(result.stdout)
    except json.JSONDecodeError as exc:
        return report(False, f"salida JSON inválida de docker compose ps: {exc}")

    by_service = {record.get("Service"): record for record in records}
    missing = EXPECTED_SERVICES.difference(by_service)
    if missing:
        report(False, f"servicios ausentes: {', '.join(sorted(missing))}")
        return False

    all_ok = True
    for service in sorted(EXPECTED_SERVICES):
        record = by_service[service]
        state = record.get("State", "")
        if service == "kafka-init":
            ok = state == "exited" and record.get("ExitCode") == 0
            message = f"{service}: {state}, exit code {record.get('ExitCode')}"
        else:
            ok = state == "running"
            message = f"{service}: {state}"
            if service in HEALTHY_SERVICES:
                ok = ok and record.get("Health") == "healthy"
                message += f", health {record.get('Health', 'unknown')}"
        all_ok = report(ok, message) and all_ok

    postgres_mounts = by_service["postgres"].get("Mounts", "")
    all_ok = report(bool(postgres_mounts), "postgres: volumen persistente montado") and all_ok
    return all_ok


def check_http_endpoints() -> bool:
    all_ok = True
    for service, url in HTTP_HEALTHCHECKS.items():
        try:
            with urlopen(url, timeout=5) as response:
                ok = 200 <= response.status < 300
                message = f"{service}: HTTP {response.status}"
        except (OSError, URLError) as exc:
            ok = False
            message = f"{service}: {exc}"
        all_ok = report(ok, message) and all_ok
    return all_ok


def check_topics() -> bool:
    result = run_command(
        [
            "docker",
            "compose",
            "exec",
            "-T",
            "kafka",
            "/opt/kafka/bin/kafka-topics.sh",
            "--bootstrap-server",
            "localhost:9092",
            "--list",
        ]
    )
    if result.returncode != 0:
        return report(False, f"Kafka topics: {result.stderr.strip()}")

    topics = {line.strip() for line in result.stdout.splitlines() if line.strip()}
    missing = EXPECTED_TOPICS.difference(topics)
    return report(not missing, "Kafka topics: seis topics presentes" if not missing else f"Kafka topics faltantes: {', '.join(sorted(missing))}")


def main() -> int:
    checks: Iterable[bool] = (check_containers(), check_http_endpoints(), check_topics())
    if all(checks):
        print("Plataforma saludable: contenedores, endpoints y topics verificados.")
        return 0
    print("La plataforma requiere atención.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
