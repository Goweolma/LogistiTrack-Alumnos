"""Valida la salud completa de la plataforma LogistiTrack.

Comprueba el estado de los contenedores, sus healthchecks, el DNS interno,
la red compartida, el esquema inicial, los endpoints HTTP y los seis topics.
"""

from __future__ import annotations

import json
import os
import subprocess
from collections.abc import Iterable
from pathlib import Path
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
INFRASTRUCTURE_SERVICES = {"postgres", "kafka", "kafka-init"}
# kafka-init termina y desaparece del DNS. Solo se resuelven servicios vivos.
COMPOSE_NETWORK = "logistitrack"
INIT_SQL_DESTINATION = "/docker-entrypoint-initdb.d/01-init.sql"
DNS_NAMES = (
    "postgres",
    "kafka",
    "orders",
    "inventory",
    "warehouse",
    "delivery",
    "frontend",
)
PROJECT_ROOT = Path(__file__).resolve().parents[1]


def run_command(args: list[str]) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            args, capture_output=True, text=True, check=False,
            cwd=PROJECT_ROOT, timeout=45, encoding="utf-8", errors="replace",
        )
    except OSError as exc:
        return subprocess.CompletedProcess(args, 127, "", f"No se pudo ejecutar {args[0]}: {exc}")
    except subprocess.TimeoutExpired:
        return subprocess.CompletedProcess(args, 124, "", "Tiempo agotado después de 45 segundos")


def parse_compose_records(output: str) -> list[dict]:
    """Admite un array JSON y objetos JSON por línea de Docker Compose."""
    if not output.strip():
        return []
    try:
        decoded = json.loads(output)
    except json.JSONDecodeError:
        records = [json.loads(line) for line in output.splitlines() if line.strip()]
    else:
        records = decoded if isinstance(decoded, list) else [decoded]
    if not all(isinstance(record, dict) for record in records):
        raise ValueError("Se esperaban registros JSON de contenedores")
    return records


def report(ok: bool, message: str) -> bool:
    print(f"[{'OK' if ok else 'ERROR'}] {message}")
    return ok


def service_report(ok: bool, service: str, message: str) -> bool:
    if not ok:
        category = (
            "INFRAESTRUCTURA" if service in INFRASTRUCTURE_SERVICES
            else "BLOQUEADO POR DEPENDENCIA EXTERNA"
        )
        message = f"{category}: {message}"
    return report(ok, message)


def check_postgres_volume(record: dict) -> bool:
    """Verifica destino, escritura y etiqueta Compose del volumen real."""
    container_id = record.get("ID")
    if not container_id:
        return report(False, "INFRAESTRUCTURA: postgres sin ID para inspeccionar volumen")
    result = run_command(["docker", "inspect", "--format", "{{json .Mounts}}", container_id])
    if result.returncode != 0:
        return report(False, f"INFRAESTRUCTURA: inspección de postgres: {result.stderr.strip()}")
    try:
        mounts = json.loads(result.stdout)
        if not isinstance(mounts, list) or not all(isinstance(m, dict) for m in mounts):
            raise ValueError("Mounts debe ser una lista de montajes")
    except ValueError as exc:
        return report(False, f"INFRAESTRUCTURA: montajes inválidos: {exc}")
    for mount in mounts:
        if (mount.get("Type") == "volume"
                and mount.get("Destination") == "/var/lib/postgresql/data"
                and mount.get("RW") is True and mount.get("Name")):
            result = run_command([
                "docker", "volume", "inspect", "--format", "{{json .Labels}}", mount["Name"],
            ])
            if result.returncode != 0:
                return report(False, f"INFRAESTRUCTURA: inspección del volumen: {result.stderr.strip()}")
            try:
                labels = json.loads(result.stdout)
            except ValueError as exc:
                return report(False, f"INFRAESTRUCTURA: etiquetas del volumen inválidas: {exc}")
            ok = isinstance(labels, dict) and labels.get("com.docker.compose.volume") == "postgres_data"
            return service_report(ok, "postgres", f"postgres: volumen postgres_data en /var/lib/postgresql/data ({mount['Name']})")
    return report(False, "INFRAESTRUCTURA: falta postgres_data escribible en /var/lib/postgresql/data")


def check_containers() -> bool:
    result = run_command(["docker", "compose", "ps", "--all", "--format", "json"])
    if result.returncode != 0:
        return report(False, f"INFRAESTRUCTURA: docker compose ps: {result.stderr.strip()}")

    try:
        records = parse_compose_records(result.stdout)
    except ValueError as exc:
        return report(False, f"INFRAESTRUCTURA: salida JSON inválida de docker compose ps: {exc}")

    by_service = {record.get("Service"): record for record in records}
    all_ok = True
    for service in sorted(EXPECTED_SERVICES):
        if service not in by_service:
            service_report(False, service, f"{service}: servicio ausente")
            all_ok = False
            continue
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
        all_ok = service_report(ok, service, message) and all_ok

    if "postgres" in by_service:
        all_ok = check_postgres_volume(by_service["postgres"]) and all_ok
    return all_ok


def check_shared_network() -> bool:
    """Los ocho servicios deben compartir la red que Compose llama logistitrack.

    El nombre visible de Docker puede llevar el prefijo del proyecto. La etiqueta
    com.docker.compose.network es la que declara el archivo.
    """
    result = run_command(["docker", "compose", "ps", "--all", "--format", "json"])
    if result.returncode != 0:
        return report(False, f"INFRAESTRUCTURA: red interna: {result.stderr.strip()}")
    try:
        records = parse_compose_records(result.stdout)
    except ValueError as exc:
        return report(False, f"INFRAESTRUCTURA: red interna: {exc}")

    by_service = {record.get("Service"): record for record in records}
    network_ids = []
    all_ok = True
    for service in sorted(EXPECTED_SERVICES):
        record = by_service.get(service)
        container_id = record.get("ID") if isinstance(record, dict) else None
        if not container_id:
            service_report(False, service, f"{service}: sin contenedor para comprobar la red")
            all_ok = False
            continue
        inspected = run_command([
            "docker", "inspect", "--format", "{{json .NetworkSettings.Networks}}", container_id,
        ])
        if inspected.returncode != 0:
            report(False, f"INFRAESTRUCTURA: {service}: red no inspeccionable: {inspected.stderr.strip()}")
            all_ok = False
            continue
        try:
            networks = json.loads(inspected.stdout)
            if not isinstance(networks, dict):
                raise ValueError("Se esperaba el mapa de redes del contenedor")
        except ValueError as exc:
            report(False, f"INFRAESTRUCTURA: {service}: redes inválidas: {exc}")
            all_ok = False
            continue
        if len(networks) != 1:
            report(False, f"INFRAESTRUCTURA: {service}: debe usar solo la red de Compose")
            all_ok = False
            continue
        info = next(iter(networks.values()))
        network_id = info.get("NetworkID") if isinstance(info, dict) else None
        if not network_id:
            report(False, f"INFRAESTRUCTURA: {service}: sin identificador de red")
            all_ok = False
            continue
        network_ids.append(network_id)

    if not all_ok:
        return False
    if len(set(network_ids)) != 1:
        return report(False, "INFRAESTRUCTURA: los servicios no comparten una sola red")

    labels = run_command(["docker", "network", "inspect", "--format", "{{json .Labels}}", network_ids[0]])
    if labels.returncode != 0:
        return report(False, f"INFRAESTRUCTURA: etiqueta de red: {labels.stderr.strip()}")
    try:
        decoded = json.loads(labels.stdout)
    except ValueError as exc:
        return report(False, f"INFRAESTRUCTURA: etiqueta de red inválida: {exc}")
    ok = isinstance(decoded, dict) and decoded.get("com.docker.compose.network") == COMPOSE_NETWORK
    message = (
        "Red Compose logistitrack compartida por los ocho servicios"
        if ok else "INFRAESTRUCTURA: la red compartida no es la red logistitrack de Compose"
    )
    return report(ok, message)


def check_internal_dns() -> bool:
    """Resuelve por nombre los servicios que siguen en ejecución."""
    result = run_command(["docker", "compose", "ps", "--all", "--format", "json"])
    if result.returncode != 0:
        return report(False, f"INFRAESTRUCTURA: DNS interno: {result.stderr.strip()}")
    try:
        records = parse_compose_records(result.stdout)
    except ValueError as exc:
        return report(False, f"INFRAESTRUCTURA: DNS interno: {exc}")

    running = {record.get("Service") for record in records if record.get("State") == "running"}
    if "postgres" not in running:
        return report(False, "INFRAESTRUCTURA: DNS interno: postgres no está en ejecución")
    required = [name for name in DNS_NAMES if name in running]
    script = (
        "missing=0; "
        f"for name in {' '.join(required)}; do "
        "if getent hosts \"$name\" >/dev/null; then echo OK \"$name\"; "
        "else echo FAIL \"$name\"; missing=1; fi; "
        "done; exit $missing"
    )
    probed = run_command(["docker", "compose", "exec", "-T", "postgres", "bash", "-c", script])
    resolved = set()
    failed = set()
    for line in probed.stdout.splitlines():
        parts = line.split()
        if len(parts) == 2 and parts[0] == "OK":
            resolved.add(parts[1])
        elif len(parts) == 2 and parts[0] == "FAIL":
            failed.add(parts[1])
    if resolved | failed != set(required) or probed.returncode not in (0, 1):
        detail = probed.stderr.strip() or "sin respuesta de getent"
        return report(False, f"INFRAESTRUCTURA: DNS interno: {detail}")
    missing = [name for name in required if name not in resolved]
    if not missing and not failed:
        return report(True, "DNS interno: los servicios en ejecución se resuelven por nombre")
    return report(False, "INFRAESTRUCTURA: DNS interno sin resolver: " + ", ".join(missing))


def check_init_sql() -> bool:
    """El DDL compartido debe estar montado solo lectura y no sustituye al volumen."""
    result = run_command(["docker", "compose", "ps", "--all", "--format", "json"])
    if result.returncode != 0:
        return report(False, f"INFRAESTRUCTURA: init.sql: {result.stderr.strip()}")
    try:
        records = parse_compose_records(result.stdout)
    except ValueError as exc:
        return report(False, f"INFRAESTRUCTURA: init.sql: {exc}")

    postgres = next((record for record in records if record.get("Service") == "postgres"), None)
    container_id = postgres.get("ID") if isinstance(postgres, dict) else None
    if not container_id:
        return report(False, "INFRAESTRUCTURA: postgres sin ID para inspeccionar init.sql")
    inspected = run_command(["docker", "inspect", "--format", "{{json .Mounts}}", container_id])
    if inspected.returncode != 0:
        return report(False, f"INFRAESTRUCTURA: init.sql: {inspected.stderr.strip()}")
    try:
        mounts = json.loads(inspected.stdout)
        if not isinstance(mounts, list) or not all(isinstance(mount, dict) for mount in mounts):
            raise ValueError("Mounts debe ser una lista de montajes")
    except ValueError as exc:
        return report(False, f"INFRAESTRUCTURA: init.sql: {exc}")

    for mount in mounts:
        if (mount.get("Type") == "bind"
                and mount.get("Destination") == INIT_SQL_DESTINATION
                and mount.get("RW") is False
                and mount.get("Mode") == "ro"):
            return report(True, "postgres: init.sql montado solo lectura")
    return report(False, "INFRAESTRUCTURA: falta init.sql de solo lectura en " + INIT_SQL_DESTINATION)


def check_http_endpoints() -> bool:
    all_ok = True
    for service, url in HTTP_HEALTHCHECKS.items():
        url = os.getenv(f"PLATFORM_{service.upper()}_HEALTH_URL", url)
        try:
            with urlopen(url, timeout=5) as response:
                ok = 200 <= response.status < 300
                message = f"{service}: HTTP {response.status}"
        except (OSError, URLError, ValueError) as exc:
            ok = False
            message = f"{service}: {exc}"
        all_ok = service_report(ok, service, message) and all_ok
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
        return report(False, f"INFRAESTRUCTURA: Kafka topics: {result.stderr.strip()}")

    topics = {line.strip() for line in result.stdout.splitlines() if line.strip()}
    missing = EXPECTED_TOPICS.difference(topics)
    return report(not missing, "Kafka topics: seis topics presentes" if not missing else f"INFRAESTRUCTURA: Kafka topics faltantes: {', '.join(sorted(missing))}")


def main() -> int:
    checks: Iterable[bool] = (
        check_containers(),
        check_internal_dns(),
        check_shared_network(),
        check_init_sql(),
        check_http_endpoints(),
        check_topics(),
    )
    if all(checks):
        print("Plataforma saludable: contenedores, DNS, red, init.sql, endpoints y topics verificados.")
        return 0
    print("La plataforma requiere atención. Resolver infraestructura primero; los fallos de servicios del equipo requieren revisar sus dependencias y logs.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
