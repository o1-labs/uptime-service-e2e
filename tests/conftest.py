import os
import time
from pathlib import Path

import boto3
import psycopg2
import pytest
import requests

REPO_ROOT = Path(__file__).resolve().parent.parent


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


def _dump_db_snapshot(dsn: str) -> str:
    """Quick snapshot of the validation-relevant tables, for failure triage."""
    queries = [
        ("submissions count + verified breakdown",
         "SELECT verified, validation_error IS NOT NULL AS has_error, count(*) "
         "FROM submissions GROUP BY 1, 2 ORDER BY 1, 2"),
        ("latest 5 submissions (verification fields)",
         "SELECT submitter, block_hash, verified, validation_error "
         "FROM submissions ORDER BY id DESC LIMIT 5"),
        ("nodes",
         "SELECT id, block_producer_key, score, score_percent FROM nodes"),
        ("points count by node",
         "SELECT node_id, count(*) FROM points GROUP BY 1 ORDER BY 1"),
        ("score_history count", "SELECT count(*) FROM score_history"),
        ("bot_logs latest 3", "SELECT id, files_processed, batch_start_epoch, "
         "batch_end_epoch FROM bot_logs ORDER BY id DESC LIMIT 3"),
    ]
    out = ["\n===== POSTGRES SNAPSHOT ====="]
    try:
        with psycopg2.connect(dsn) as conn:
            with conn.cursor() as cur:
                for label, sql in queries:
                    out.append(f"\n-- {label} --")
                    try:
                        cur.execute(sql)
                        rows = cur.fetchall()
                        if not rows:
                            out.append("  (empty)")
                        else:
                            for r in rows:
                                out.append(f"  {r}")
                    except Exception as e:
                        out.append(f"  ERROR: {e}")
    except Exception as e:
        out.append(f"\nconnection failed: {e}")
    return "\n".join(out)


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item, call):
    """When a test fails, attach a Postgres state dump to the report.

    Validation correctness depends on a chain of triggers + cross-table state,
    so per-test snapshots are far more useful than digging through validation
    container logs after the fact.
    """
    outcome = yield
    report = outcome.get_result()
    if report.when == "call" and report.failed:
        dsn = os.environ.get(
            "POSTGRES_DSN",
            "host=localhost port=55432 user=postgres password=postgres "
            "dbname=delegation_program sslmode=disable",
        )
        snapshot = _dump_db_snapshot(dsn)
        report.sections.append(("Postgres snapshot at failure", snapshot))
