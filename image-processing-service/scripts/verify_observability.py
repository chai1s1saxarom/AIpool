#!/usr/bin/env python3
"""
Генерация тестового трафика для проверки метрик и JSON-логов.
Запуск: python scripts/verify_observability.py [--base-url http://localhost:8000]
"""
from __future__ import annotations

import argparse
import sys
import uuid

import httpx


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://localhost:8000")
    args = parser.parse_args()
    base = args.base_url.rstrip("/")
    correlation = str(uuid.uuid4())

    with httpx.Client(timeout=30.0) as client:
        print("1. Нормальный запрос (health)...")
        r = client.get(f"{base}/v1/health/liveness", headers={"X-Request-ID": correlation})
        print(f"   status={r.status_code}, X-Request-ID={r.headers.get('X-Request-ID')}")

        print("2. Ошибочный запрос (404)...")
        r = client.get(f"{base}/v1/images/{uuid.uuid4()}")
        print(f"   status={r.status_code}")

        print("3. Медленный запрос (~2s)...")
        r = client.get(f"{base}/v1/debug/slow", params={"delay": 2})
        print(f"   status={r.status_code}")

        print("4. Метрики Prometheus...")
        r = client.get(f"{base}/metrics")
        print(f"   status={r.status_code}, bytes={len(r.content)}")
        if "http_requests_total" not in r.text:
            print("   WARN: http_requests_total не найден в /metrics", file=sys.stderr)
            return 1

    print("\nГотово. Проверьте:")
    print("  - Prometheus targets: http://localhost:9090/targets")
    print("  - Grafana: http://localhost:3000 (admin/admin)")
    print("  - JSON-логи в консоли контейнера app (поле correlation_id)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
