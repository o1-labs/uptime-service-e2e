"""Coverage that minimina BPs actually submit to the backend.

Used to POST a canned 2021 fixture; now the real mina-daemons in the
sibling minimina network produce blocks, sign submissions with their
genesis-ledger BP keys, and POST to backend:8080. We just poll for them
to arrive.

Slow side: mina-daemons take 15–30 min to bootstrap on a fresh
minimina network before the first block lands. The wait is absorbed
once by the `first_submission_arrived` session fixture.
"""

import pytest

# Public keys of the BPs in fixtures/minimina/topology.json. Any submission
# the backend records must originate from one of these — otherwise the
# minimina stack is misconfigured or signature verification is letting
# stray traffic through.
EXPECTED_SUBMITTERS = {
    "B62qoEykaCCyw6JtF3EM4S33FpCon5F4HiZbgby5oPSgpVQ6MYYfxPC",  # node-a
    "B62qiZv3JwF9wRGtqhNbLsfWMm6zYd71RD6Akfq9AUK8MY4EC5Ye9i6",  # node-b
    "B62qoztWpP8cJbknVWCcW2u56Y44wLNqpsompb5dDGoG1o6nfeatTKX",  # node-c
}


def test_minimina_bps_submit_to_backend(first_submission_arrived, db, s3, s3_bucket, s3_prefix):
    # `first_submission_arrived` blocks at session scope until at least one
    # row exists. By the time we get here, the rows are present.
    with db.cursor() as cur:
        cur.execute(
            "SELECT submitter, block_hash FROM submissions ORDER BY id LIMIT 5"
        )
        rows = cur.fetchall()
    assert rows, "first_submission_arrived returned but submissions table is empty"

    submitters = {r[0] for r in rows}
    unknown = submitters - EXPECTED_SUBMITTERS
    assert not unknown, (
        f"submissions came from unexpected pubkeys: {unknown} — either the "
        f"topology drifted or signature verification is off"
    )

    # The backend should have written the block bytes to S3 alongside the row.
    # Pick one, confirm the object exists.
    sample = rows[0]
    block_hash = sample[1]
    block_key = f"{s3_prefix}/blocks/{block_hash}.dat"
    head = s3.head_object(Bucket=s3_bucket, Key=block_key)
    assert head["ContentLength"] > 0, f"empty block at {block_key}"
