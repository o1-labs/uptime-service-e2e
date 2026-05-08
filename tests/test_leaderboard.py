"""Smoke coverage for the delegation-program-leaderboard API.

The leaderboard is a thin Flask wrapper over the same Postgres the validation
coordinator writes to. We assert two things:

- /health returns 200 — the Flask app is up.
- /health/ready returns 200 — the DB connection is wired correctly,
  meaning the schema this leaderboard build expects matches what the
  validation repo's create_tables.sql defines.

Both run independently of any submission flow, so this test stays fast and
isn't gated on the slow worker run in test_validation.
"""

import os

import pytest
import requests


@pytest.fixture(scope="session")
def leaderboard_url() -> str:
    return os.environ.get("LEADERBOARD_API_URL", "http://localhost:55000")


def test_leaderboard_health(leaderboard_url):
    response = requests.get(f"{leaderboard_url}/health", timeout=5)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body.get("status") == "healthy"


def test_leaderboard_db_ready(leaderboard_url):
    """Readiness probe — proves the leaderboard can talk to the same Postgres
    schema the validation repo defines."""
    response = requests.get(f"{leaderboard_url}/health/ready", timeout=10)
    assert response.status_code == 200, response.text
