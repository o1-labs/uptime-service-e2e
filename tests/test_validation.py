"""End-to-end coverage of the verification loop.

Submission → backend → S3 + Postgres → validation coordinator → submission-updater
worker → row updated with verification outcome.

This test only asserts that the row was *touched* by the validation pipeline
(`state_hash`, `verified`, or `validation_error` becomes non-null). It does not
assert that the block actually validates — the canned `req-no-snark.json` is
old test data whose block format the current worker can't decode, so it always
ends up with `validation_error="Fail to decode block"`. That's fine for a
plumbing test: it proves the pipeline runs end-to-end without exercising
consensus correctness, which lives in unit tests upstream.
"""

import subprocess
import time
from pathlib import Path

import pytest
import requests

from .conftest import reset_bot_logs

REPO_ROOT = Path(__file__).resolve().parent.parent


def _stop_validation():
    """Stop the validation container so it doesn't keep catching up batches
    forever in the background after this test passes. Without this, leaving
    a host suspended for hours leads to confusing wall-clock results on the
    next run."""
    subprocess.run(
        [
            "docker", "compose",
            "-f", str(REPO_ROOT / "compose" / "docker-compose.yaml"),
            "--env-file", str(REPO_ROOT / ".env"),
            "stop", "validation",
        ],
        check=False,
        capture_output=True,
    )


@pytest.mark.timeout(600)
def test_submission_gets_processed_by_validation(
    backend_ready, backend_url, canned_submission, db, s3, s3_bucket, s3_prefix, clean_state
):
    response = requests.post(
        f"{backend_url}/v1/submit",
        json=canned_submission,
        timeout=10,
    )
    assert response.status_code == 200, response.text

    # Move the submission's wall-clock time into the past relative to
    # validation's batch boundary, then force the coordinator to re-read
    # bot_logs from a recent point. After the wait, the batch containing
    # this submission will have `batch_end < now`, so the coordinator
    # processes it immediately on restart instead of triggering its
    # hardcoded 2-minute "wait until batch ends" delta.
    time.sleep(70)
    reset_bot_logs(db, seconds_ago=90)

    submitter = canned_submission["submitter"]
    # The worker (submission-updater) doesn't honor AWS_ENDPOINT_URL_S3, so it
    # tries to fetch blocks from real AWS, fails with NoSuchBucket, and then
    # delegation-verify runs on bad data for ~4 minutes before exiting. Until
    # submission-updater gets the same env-var patch we landed in the backend,
    # the worker run is slow but eventually writes a row update.
    deadline = time.monotonic() + 360
    last = None
    while time.monotonic() < deadline:
        with db.cursor() as cur:
            cur.execute(
                "SELECT state_hash, verified, validation_error FROM submissions "
                "WHERE submitter = %s",
                (submitter,),
            )
            last = cur.fetchone()
        if last is not None:
            state_hash, verified, validation_error = last
            if state_hash is not None or verified is not None or validation_error is not None:
                _stop_validation()
                return
        time.sleep(2)

    _stop_validation()
    assert False, (
        f"submission for {submitter} was not processed by validation "
        f"within deadline; last row state: {last}"
    )
