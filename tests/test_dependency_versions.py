"""Las dependencias compartidas usan la misma versión en toda la plataforma."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CANONICAL = {
    "Flask": "3.1.0",
    "gunicorn": "23.0.0",
    "psycopg[binary]": "3.2.3",
    "confluent-kafka": "2.6.1",
    "requests": "2.32.3",
    "pytest": "8.3.4",
    "jsonschema": "4.23.0",
}


def _pins(path: Path) -> dict[str, str]:
    found = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "==" not in line:
            continue
        name, version = line.split("==", 1)
        found[name.strip()] = version.strip()
    return found


def test_shared_packages_use_one_version():
    files = [ROOT / "requirements-dev.txt", *sorted((ROOT / "services").glob("*/requirements.txt"))]

    for path in files:
        for name, version in _pins(path).items():
            assert name in CANONICAL, f"{path.name} agrega {name} sin versión canónica"
            assert version == CANONICAL[name], f"{path} fija {name}=={version}"
