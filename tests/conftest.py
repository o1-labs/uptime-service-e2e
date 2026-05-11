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
