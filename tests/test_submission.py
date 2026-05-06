import requests


def test_submission_lands_in_postgres_and_s3(
    backend_ready, backend_url, canned_submission, db, s3, s3_bucket, s3_prefix, clean_state
):
    response = requests.post(
        f"{backend_url}/v1/submit",
        json=canned_submission,
        timeout=10,
    )
    assert response.status_code == 200, response.text
    assert response.json() == {"status": "ok"}

    submitter = canned_submission["submitter"]
    with db.cursor() as cur:
        cur.execute(
            "SELECT submitter, block_hash, peer_id FROM submissions WHERE submitter = %s",
            (submitter,),
        )
        rows = cur.fetchall()

    assert len(rows) == 1, f"expected exactly one submission row, got {rows}"
    row_submitter, block_hash, peer_id = rows[0]
    assert row_submitter == submitter
    assert peer_id == canned_submission["data"]["peer_id"]

    # S3: block .dat under <prefix>/blocks/<block_hash>.dat
    block_key = f"{s3_prefix}/blocks/{block_hash}.dat"
    block_head = s3.head_object(Bucket=s3_bucket, Key=block_key)
    assert block_head["ContentLength"] > 0, f"empty block at {block_key}"

    # S3: submission metadata JSON under <prefix>/submissions/<date>/...<submitter>.json
    # We don't know the exact timestamp, so list and find the one for this submitter.
    listing = s3.list_objects_v2(Bucket=s3_bucket, Prefix=f"{s3_prefix}/submissions/")
    matching = [o["Key"] for o in listing.get("Contents", []) if submitter in o["Key"]]
    assert len(matching) == 1, f"expected one metadata object for {submitter}, got {matching}"
