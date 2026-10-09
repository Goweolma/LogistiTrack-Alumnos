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


@pytest.mark.parametrize("labels", [
    "com.docker.compose.oneoff=True,com.docker.compose.service=kafka-init",
    {"com.docker.compose.oneoff": "True"},
])
def test_auxiliary_run_does_not_replace_completed_init(monkeypatch, labels):
    records = healthy_records() + [{"Service": "kafka-init", "State": "running", "Labels": labels}]
    mock_docker(monkeypatch, records=records)
    assert health.check_containers()


def test_auxiliary_run_does_not_hide_missing_service(monkeypatch):
    records = [record for record in healthy_records() if record["Service"] != "kafka-init"]
    records.append({"Service": "kafka-init", "State": "exited", "ExitCode": 0,
                    "Labels": "com.docker.compose.oneoff=True"})
    mock_docker(monkeypatch, records=records)
    assert not health.check_containers()


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


@pytest.mark.parametrize("service", ["inventory", "warehouse", "delivery", "frontend"])
@pytest.mark.parametrize("status", ["unhealthy", "starting", ""])
def test_running_service_requires_successful_docker_healthcheck(monkeypatch, service, status):
    records = healthy_records()
    next(record for record in records if record["Service"] == service)["Health"] = status
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


@pytest.mark.parametrize("failed", [None, "check_containers", "check_http_endpoints", "check_topics"])
def test_exit_code_and_all_checks_run(monkeypatch, failed):
    called = []
    for name in ("check_containers", "check_http_endpoints", "check_topics"):
        def check(name=name):
            called.append(name)
            return name != failed
        monkeypatch.setattr(health, name, check)
    assert health.main() == (0 if failed is None else 1)
    assert called == ["check_containers", "check_http_endpoints", "check_topics"]
