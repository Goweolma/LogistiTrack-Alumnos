"""Comprueba únicamente que la base proporcionada arranca correctamente."""

import sys

import requests


URLS = {
    "frontend": "http://localhost:8080/frontend-health",
    "orders": "http://localhost:5001/health",
    "inventory": "http://localhost:5002/health",
    "warehouse": "http://localhost:5003/health",
    "delivery": "http://localhost:5004/health",
}


def main() -> int:
    failed = []
    for service, url in URLS.items():
        try:
            response = requests.get(url, timeout=5)
            response.raise_for_status()
            print(f"[OK] {service}: {response.status_code}")
        except requests.RequestException as exc:
            failed.append(service)
            print(f"[ERROR] {service}: {exc}")

    if failed:
        print(f"Base incompleta. Servicios con error: {', '.join(failed)}")
        return 1

    print("Base lista. El equipo puede comenzar la implementación.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

