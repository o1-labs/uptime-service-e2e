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


@pytest.mark.timeout(3600)
def test_validated_bp_reaches_scoreboard(leaderboard_url, db):
    """After verified submissions accumulate, the validation coordinator
    inserts a `points` row per verified-batch + writes a nodes/score_history
    entry that the leaderboard surfaces via /uptimescore/<bp>.

    We poll the DB directly first — `points` count > 0 is the canonical
    signal that validation processed at least one verified submission. The
    leaderboard endpoint is a downstream view that depends on the
    `update_scoreboard` window populating, which we check separately.
    """
    deadline = time.monotonic() + 3000
    while time.monotonic() < deadline:
        with db.cursor() as cur:
            cur.execute("SELECT count(*) FROM points")
            (points_count,) = cur.fetchone()
            if points_count > 0:
                break
        time.sleep(15)
    else:
        pytest.fail(
            "no rows ever landed in `points` — validation never accepted a "
            "submission for scoring (most likely all delegation-verify runs "
            "rejected the blocks)"
        )

    # Sanity: the BP credited in `points` should be one of our minimina BPs.
    with db.cursor() as cur:
        cur.execute(
            "SELECT DISTINCT n.block_producer_key FROM points p "
            "JOIN nodes n ON p.node_id = n.id"
        )
        bps_with_points = {r[0] for r in cur.fetchall()}
    unknown = bps_with_points - set(KNOWN_BPS)
    assert not unknown, f"unexpected BPs got points: {unknown}"
    assert bps_with_points, "points rows exist but couldn't join back to a known BP"

    # Now confirm the leaderboard API surfaces at least one of them. The
    # endpoint returns 404 when the BP has no score_history yet; that can lag
    # behind points (depends on `update_scoreboard` having run), so we poll.
    deadline = time.monotonic() + 600
    while time.monotonic() < deadline:
        for bp in bps_with_points:
            r = requests.get(f"{leaderboard_url}/uptimescore/{bp}", timeout=10)
            if r.status_code == 200:
                return
        time.sleep(15)

    pytest.fail(
        "points table has entries but the leaderboard endpoint never returned "
        "200 for any of them — the scoreboard population step in validation "
        "may not have run"
    )
