"""Coverage for the delegation-program-leaderboard API.

Plumbing layer:
  - /health proves the Flask app is up
  - /health/ready proves the leaderboard's expected schema matches what
    validation's create_tables.sql defines.

Scoring layer:
  - /uptimescore/<pubkey> returns the rolling uptime score the validation
    coordinator writes via its scoreboard trigger. Once at least one
    submission has been verified, this should return a row for the BP.
    Slow path because we depend on the full minimina → backend →
    validation → scoreboard chain.
"""

import os
import time

import pytest
import requests


# Same set as test_submission.EXPECTED_SUBMITTERS — duplicated here to keep
# tests independently importable; a fixture would be overkill.
KNOWN_BPS = (
    "B62qoEykaCCyw6JtF3EM4S33FpCon5F4HiZbgby5oPSgpVQ6MYYfxPC",  # node-a
    "B62qiZv3JwF9wRGtqhNbLsfWMm6zYd71RD6Akfq9AUK8MY4EC5Ye9i6",  # node-b
    "B62qoztWpP8cJbknVWCcW2u56Y44wLNqpsompb5dDGoG1o6nfeatTKX",  # node-c
)


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


@pytest.mark.timeout(1200)
def test_leaderboard_shows_scoring_bps(leaderboard_url, db):
    """A BP that has at least one verified submission should appear in the
    scoreboard. This depends on the validation coordinator's `points` and
    `scoreboard` triggers running — so it's gated on test_validation's
    happy path. Independent of test ordering: this poll waits anyway.
    """
    deadline = time.monotonic() + 1150
    last_seen = None
    while time.monotonic() < deadline:
        # First confirm scoreboard has *any* row — query the API.
        for bp in KNOWN_BPS:
            r = requests.get(
                f"{leaderboard_url}/uptimescore/{bp}", timeout=10
            )
            if r.status_code == 200:
                body = r.json()
                last_seen = (bp, body)
                # The endpoint returns a list of score records per BP; any
                # row with a non-null score_percent counts.
                if isinstance(body, list) and any(
                    rec.get("score_percent") is not None for rec in body
                ):
                    return
        time.sleep(5)

    pytest.fail(f"no BP reached the leaderboard scoreboard; last response: {last_seen}")
