#!/usr/bin/env python3
"""Trim the docker-compose.yaml minimina generated for our network.

Removes a placeholder service we only kept in topology.json so minimina
adds `--uptime-url http://<service>-<network-id>:8080/v1/submit` to BPs'
command lines. The real backend lives in our e2e compose stack; we
expose the same hostname there as a network alias and connect the BP
containers to that network after start (see Makefile minimina-up).
"""
import argparse
import sys
from pathlib import Path

try:
    import yaml
except ImportError:
    print("PyYAML missing — install dev deps with `pip install -e .`.", file=sys.stderr)
    sys.exit(2)


def patch(compose_path: Path, dummy_service: str) -> None:
    with compose_path.open() as f:
        compose = yaml.safe_load(f)

    services = compose.get("services", {})
    if dummy_service in services:
        del services[dummy_service]

    volumes = compose.get("volumes") or {}
    if dummy_service in volumes:
        del volumes[dummy_service]
        compose["volumes"] = volumes

    # `version` is deprecated in compose v2 and minimina still emits it,
    # producing a warning on every docker compose invocation. Drop it.
    compose.pop("version", None)

    with compose_path.open("w") as f:
        yaml.safe_dump(compose, f, sort_keys=False)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("compose_path", type=Path)
    parser.add_argument("--dummy-service", required=True,
                        help="name of the placeholder uptime-service-backend service to drop")
    args = parser.parse_args()
    patch(args.compose_path, args.dummy_service)
