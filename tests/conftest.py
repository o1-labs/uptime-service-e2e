import json
import os
import time
from pathlib import Path

import boto3
import psycopg2
import pytest
import requests

REPO_ROOT = Path(__file__).resolve().parent.parent
FIXTURES_DIR = REPO_ROOT / "fixtures"


@pytest.fixture(scope="session")
def backend_url() -> str:
    return os.environ.get("BACKEND_URL", "http://localhost:8080")


@pytest.fixture(scope="session")
def postgres_dsn() -> str:
    return os.environ.get(
        "POSTGRES_DSN",
        "host=localhost port=55432 user=postgres password=postgres dbname=delegation_program sslmode=disable",
    )


@pytest.fixture(scope="session")
def s3_endpoint() -> str:
    return os.environ.get("S3_ENDPOINT", "http://localhost:59000")


@pytest.fixture(scope="session")
def s3_bucket() -> str:
    return os.environ.get("E2E_BUCKET", "test-uptime")


@pytest.fixture(scope="session")
def s3_prefix() -> str:
    # Matches `network_name` in compose/config/backend.json — used as the
    # bucket key prefix by the backend (see main_bpu.go AwsContext.Prefix).
    return os.environ.get("E2E_NETWORK_NAME", "e2e")


@pytest.fixture(scope="session")
def s3(s3_endpoint):
    return boto3.client(
        "s3",
        endpoint_url=s3_endpoint,
        aws_access_key_id=os.environ.get("AWS_ACCESS_KEY_ID", "minio"),
        aws_secret_access_key=os.environ.get("AWS_SECRET_ACCESS_KEY", "minio12345"),
        region_name="us-east-1",
        config=boto3.session.Config(signature_version="s3v4", s3={"addressing_style": "path"}),
    )


@pytest.fixture(scope="session")
def backend_ready(backend_url):
    deadline = time.time() + 60
    last_err = None
    while time.time() < deadline:
        try:
            r = requests.get(f"{backend_url}/health", timeout=2)
            if r.status_code == 200:
                return
        except requests.RequestException as e:
            last_err = e
        time.sleep(1)
    pytest.fail(f"backend at {backend_url} did not become healthy: {last_err}")


@pytest.fixture
def db(postgres_dsn):
    conn = psycopg2.connect(postgres_dsn)
    conn.autocommit = True
    try:
        yield conn
    finally:
        conn.close()


@pytest.fixture
def canned_submission():
    with (FIXTURES_DIR / "req-no-snark.json").open() as f:
        return json.load(f)


@pytest.fixture
def clean_state(db, s3, s3_bucket, s3_prefix):
    """Reset Postgres + S3 to a known empty state before each test that uses it.

    Without this, leftover rows/objects from earlier runs make per-test
    assertions ambiguous. Each test owns its own bucket prefix slice.
    """
    with db.cursor() as cur:
        cur.execute("TRUNCATE TABLE submissions RESTART IDENTITY")
        # bot_logs has FK from points/points_summary/bot_logs_statehash, so cascade
        cur.execute("TRUNCATE TABLE bot_logs RESTART IDENTITY CASCADE")
    paginator = s3.get_paginator("list_objects_v2")
    keys = [
        {"Key": obj["Key"]}
        for page in paginator.paginate(Bucket=s3_bucket, Prefix=f"{s3_prefix}/")
        for obj in page.get("Contents", [])
    ]
    if keys:
        s3.delete_objects(Bucket=s3_bucket, Delete={"Objects": keys})


def reset_bot_logs(db, seconds_ago: int = 120):
    """Reset the validation coordinator's batch progress and force it to re-read.

    The coordinator caches `bot_logs` state in memory and doesn't re-poll
    between iterations, so simply rewriting the table is invisible to a
    running coordinator. Restart the validation container after rewriting
    so its next loop reads the fresh boundary.

    `seconds_ago` should be > SURVEY_INTERVAL_MINUTES * 60 so the next
    batch window overlaps "now," guaranteeing in-flight submissions land
    in a catch-up batch (which iterates without the coordinator's
    hardcoded 2-minute sleep delta).
    """
    import subprocess

    with db.cursor() as cur:
        cur.execute("TRUNCATE TABLE bot_logs RESTART IDENTITY CASCADE")
        cur.execute(
            """
            INSERT INTO bot_logs (
                processing_time, files_processed, file_timestamps,
                batch_start_epoch, batch_end_epoch
            ) VALUES (
                0, -1,
                NOW() - make_interval(secs => %s),
                EXTRACT(EPOCH FROM NOW() - make_interval(secs => %s))::BIGINT,
                EXTRACT(EPOCH FROM NOW() - make_interval(secs => %s))::BIGINT
            )
            """,
            (seconds_ago, seconds_ago, seconds_ago),
        )
    subprocess.run(
        [
            "docker", "compose",
            "-f", str(REPO_ROOT / "compose" / "docker-compose.yaml"),
            "--env-file", str(REPO_ROOT / ".env"),
            "restart", "validation",
        ],
        check=True,
    )
