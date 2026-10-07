"""Regresiones del diagnóstico; Docker/HTTP se simulan en el límite de I/O."""

import json
import subprocess
from urllib.error import HTTPError

import pytest

from scripts import health_platform as health


def result(stdout="", code=0, stderr=""):
    return subprocess.CompletedProcess([], code, stdout, stderr)


def healthy_records():
    return [
        {"Service": service, "ID": service + "-id", "State": "exited" if service == "kafka-init" else "running",
         "Health": "healthy", "ExitCode": 0}
        for service in sorted(health.EXPECTED_SERVICES)
    ]


def healthy_mount(**changes):
    return {"Type": "volume", "Name": "demo_postgres_data", "RW": True,
            "Destination": "/var/lib/postgresql/data", **changes}


def mock_docker(monkeypatch, records=None, mounts=None, label="postgres_data"):
    def run(args):
        if args[:3] == ["docker", "compose", "ps"]:
            return result(json.dumps(healthy_records() if records is None else records))
        if args[:2] == ["docker", "inspect"]:
            return result(json.dumps([healthy_mount()] if mounts is None else mounts))
        if args[:3] == ["docker", "volume", "inspect"]:
            return result(json.dumps({"com.docker.compose.volume": label}))
        raise AssertionError(f"Comando inesperado: {args}")
    monkeypatch.setattr(health, "run_command", run)


@pytest.mark.parametrize("output,expected", [
    ("", []), ("[]", []), ('{"Service":"kafka"}', [{"Service": "kafka"}]),
    ('[\n{"Service":"kafka"}\n]', [{"Service": "kafka"}]),
    ('{"Service":"kafka"}\n{"Service":"postgres"}\n', [{"Service": "kafka"}, {"Service": "postgres"}]),
])
def test_compose_json_formats(output, expected):
    assert health.parse_compose_records(output) == expected


@pytest.mark.parametrize("output", ["not json", "null", "[1]", '"text"'])
def test_invalid_compose_json(output):
    with pytest.raises(ValueError):
        health.parse_compose_records(output)


def test_healthy_platform_containers(monkeypatch):
    mock_docker(monkeypatch)
    assert health.check_containers()


@pytest.mark.parametrize("changes", [
    {"Type": "bind"}, {"Destination": "/docker-entrypoint-initdb.d/01-init.sql"},
    {"RW": False}, {"Name": ""},
])
def test_non_persistent_or_wrong_mount_fails(monkeypatch, changes):
    mock_docker(monkeypatch, mounts=[healthy_mount(**changes)])
    assert not health.check_containers()


def test_unrelated_named_volume_fails(monkeypatch):
    mock_docker(monkeypatch, label="other_data")
    assert not health.check_containers()


@pytest.mark.parametrize("service,changes", [
    ("kafka-init", {"ExitCode": 1}), ("kafka-init", {"State": "running"}),
    ("postgres", {"Health": "unhealthy"}), ("kafka", {"State": "exited"}),
    ("orders", {"Health": "starting"}),
])
def test_container_failure_is_not_hidden(monkeypatch, service, changes):
    records = healthy_records()
    next(record for record in records if record["Service"] == service).update(changes)
    mock_docker(monkeypatch, records=records)
    assert not health.check_containers()


def test_missing_external_service_does_not_hide_infrastructure_checks(monkeypatch, capsys):
    records = [r for r in healthy_records() if r["Service"] != "inventory"]
    mock_docker(monkeypatch, records=records)
    assert not health.check_containers()
    output = capsys.readouterr().out
    assert "BLOQUEADO POR DEPENDENCIA EXTERNA: inventory" in output
    assert "postgres: volumen postgres_data" in output


@pytest.mark.parametrize("failure,code", [
    (FileNotFoundError("docker ausente"), 127),
    (subprocess.TimeoutExpired(["docker"], 45), 124),
])
def test_docker_execution_errors_are_reported(monkeypatch, failure, code):
    def run(*args, **kwargs):
        raise failure
    monkeypatch.setattr(health.subprocess, "run", run)
    response = health.run_command(["docker", "compose", "ps"])
    assert response.returncode == code
    assert response.stderr
    assert not health.check_containers()
    assert not health.check_topics()


def test_commands_use_repository_from_any_working_directory(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    captured = {}
    def run(args, **kwargs):
        captured.update(kwargs)
        return result()
    monkeypatch.setattr(health.subprocess, "run", run)
    health.run_command(["docker", "compose", "ps"])
    assert captured["cwd"] == health.PROJECT_ROOT
    assert captured["timeout"] == 45


@pytest.mark.parametrize("missing", [None, "dead-letter"])
def test_all_six_topics_are_required(monkeypatch, missing):
    topics = health.EXPECTED_TOPICS - ({missing} if missing else set())
    monkeypatch.setattr(health, "run_command", lambda args: result("\n".join(topics | {"__consumer_offsets"})))
    assert health.check_topics() is (missing is None)


def test_http_failure_is_external_and_other_endpoints_are_checked(monkeypatch, capsys):
    monkeypatch.setattr(health, "HTTP_HEALTHCHECKS", {"orders": "http://orders/health", "inventory": "http://inventory/health"})
    monkeypatch.setenv("PLATFORM_ORDERS_HEALTH_URL", "http://custom/health")
    urls = []
    def open_url(url, timeout):
        urls.append(url)
        raise HTTPError(url, 503, "unavailable", {}, None)
    monkeypatch.setattr(health, "urlopen", open_url)
    assert not health.check_http_endpoints()
    assert urls == ["http://custom/health", "http://inventory/health"]
    assert "BLOQUEADO POR DEPENDENCIA EXTERNA" in capsys.readouterr().out


def init_mount(**changes):
    mount = {
        "Type": "bind",
        "Destination": "/docker-entrypoint-initdb.d/01-init.sql",
        "Mode": "ro",
        "RW": False,
    }
    mount.update(changes)
    return mount


def mock_init_sql(monkeypatch, mounts, inspect_code=0):
    def run(args):
        if args[:3] == ["docker", "compose", "ps"]:
            return result(json.dumps(healthy_records()))
        if args[:2] == ["docker", "inspect"]:
            if inspect_code:
                return result("", inspect_code, "inspect failed")
            return result(json.dumps(mounts))
        raise AssertionError(args)

    monkeypatch.setattr(health, "run_command", run)


def test_init_sql_requires_a_read_only_bind_next_to_the_data_volume(monkeypatch):
    mock_init_sql(monkeypatch, [healthy_mount(), init_mount()])
    assert health.check_init_sql()


@pytest.mark.parametrize("changes", [
    {"RW": True},
    {"Mode": "rw"},
    {"Type": "volume"},
    {"Destination": "/tmp/init.sql"},
])
def test_init_sql_rejects_a_writable_or_misplaced_mount(monkeypatch, changes):
    mock_init_sql(monkeypatch, [healthy_mount(), init_mount(**changes)])
    assert not health.check_init_sql()


def test_init_sql_reports_inspect_errors(monkeypatch):
    mock_init_sql(monkeypatch, [], inspect_code=1)
    assert not health.check_init_sql()


def test_internal_dns_resolves_running_services(monkeypatch):
    def run(args):
        if args[:3] == ["docker", "compose", "ps"]:
            return result(json.dumps(healthy_records()))
        assert args[:5] == ["docker", "compose", "exec", "-T", "postgres"]
        assert "kafka-init" not in args[-1]
        return result("\n".join(f"OK {name}" for name in health.DNS_NAMES))

    monkeypatch.setattr(health, "run_command", run)
    assert health.check_internal_dns()


def test_internal_dns_skips_a_stopped_external_service(monkeypatch):
    records = healthy_records()
    next(record for record in records if record["Service"] == "inventory").update({"State": "exited"})

    def run(args):
        if args[:3] == ["docker", "compose", "ps"]:
            return result(json.dumps(records))
        probed = args[-1].split("for name in ", 1)[1].split(";", 1)[0]
        assert probed.split() == [name for name in health.DNS_NAMES if name != "inventory"]
        return result("\n".join(f"OK {name}" for name in probed.split()))

    monkeypatch.setattr(health, "run_command", run)
    assert health.check_internal_dns()


def test_internal_dns_reports_an_unresolved_running_service(monkeypatch, capsys):
    def run(args):
        if args[:3] == ["docker", "compose", "ps"]:
            return result(json.dumps(healthy_records()))
        lines = [f"FAIL {name}" if name == "kafka" else f"OK {name}" for name in health.DNS_NAMES]
        return result("\n".join(lines), code=1)

    monkeypatch.setattr(health, "run_command", run)
    assert not health.check_internal_dns()
    assert "INFRAESTRUCTURA: DNS interno sin resolver: kafka" in capsys.readouterr().out


def test_internal_dns_requires_a_running_postgres(monkeypatch):
    records = healthy_records()
    next(record for record in records if record["Service"] == "postgres").update({"State": "exited"})
    monkeypatch.setattr(health, "run_command", lambda args: result(json.dumps(records)))
    assert not health.check_internal_dns()


def network_payload(network_id="net-1", name="logistitrack-alumnos_logistitrack"):
    return json.dumps({name: {"NetworkID": network_id, "IPAddress": ""}})


def labels_payload(network="logistitrack"):
    return json.dumps({"com.docker.compose.network": network, "com.docker.compose.project": "logistitrack-alumnos"})


def mock_network(monkeypatch, records=None, networks=None, labels=labels_payload(), inspect_code=0):
    def run(args):
        if args[:3] == ["docker", "compose", "ps"]:
            return result(json.dumps(healthy_records() if records is None else records))
        if args[:2] == ["docker", "inspect"]:
            if inspect_code != 0:
                return result("", inspect_code, "inspect failed")
            payload = networks(args[-1]) if callable(networks) else (networks or network_payload())
            return result(payload)
        if args[:2] == ["docker", "network"]:
            return result(labels)
        raise AssertionError(args)

    monkeypatch.setattr(health, "run_command", run)


def test_shared_network_accepts_project_prefix_when_label_matches(monkeypatch):
    mock_network(monkeypatch)
    assert health.check_shared_network()


def test_shared_network_rejects_a_split_or_unlabeled_network(monkeypatch):
    mock_network(monkeypatch, networks=lambda container: network_payload("other" if container == "delivery-id" else "net-1"))
    assert not health.check_shared_network()
    mock_network(monkeypatch, labels=labels_payload("other"))
    assert not health.check_shared_network()


def test_shared_network_rejects_extra_networks_and_missing_containers(monkeypatch, capsys):
    mock_network(monkeypatch, networks=json.dumps({
        "logistitrack": {"NetworkID": "net-1"},
        "extra": {"NetworkID": "net-2"},
    }))
    assert not health.check_shared_network()
    records = [record for record in healthy_records() if record["Service"] != "inventory"]
    mock_network(monkeypatch, records=records)
    assert not health.check_shared_network()
    assert "BLOQUEADO POR DEPENDENCIA EXTERNA: inventory" in capsys.readouterr().out


def test_internal_dns_reports_probe_failures(monkeypatch):
    def run(args):
        if args[:3] == ["docker", "compose", "ps"]:
            return result(json.dumps(healthy_records()))
        return result("", code=1, stderr="service postgres is not running")

    monkeypatch.setattr(health, "run_command", run)
    assert not health.check_internal_dns()


@pytest.mark.parametrize(
    "failed",
    [
        None, "check_containers", "check_internal_dns", "check_shared_network",
        "check_init_sql", "check_http_endpoints", "check_topics",
    ],
)
def test_exit_code_and_all_checks_run(monkeypatch, failed):
    called = []
    checks = (
        "check_containers", "check_internal_dns", "check_shared_network",
        "check_init_sql", "check_http_endpoints", "check_topics",
    )
    for name in checks:
        def check(name=name):
            called.append(name)
            return name != failed
        monkeypatch.setattr(health, name, check)
    assert health.main() == (0 if failed is None else 1)
    assert called == list(checks)
