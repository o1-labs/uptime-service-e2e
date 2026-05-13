"""Coverage that validation actually verifies the blocks minimina produces.

Real-flow validation: minimina BPs submit real signed blocks → backend stores
to MinIO + Postgres → validation coordinator picks them up on its next batch
cycle → submission-updater spawns the bundled mina-delegation-verify with
`--config-file` pointing at our minimina genesis (baked into the worker image)
→ row is marked `verified=true` with non-null `state_hash`.

If `verified` ever ends up `false` with a non-null `validation_error`, that's a
hard fail — it means the worker can decode the block (so the wiring works)
but consensus checks rejected it. Causes worth investigating in that case:
  - worker image bin_prot version drifted from mina-daemon image
  - GENESIS_LEDGER_FILE not actually being applied
  - bucket/network_name mismatch (block on disk, but not where verifier reads).
"""

import time

import pytest


@pytest.mark.timeout(600)
def test_minimina_submissions_get_verified(first_submission_arrived, db):
    # Submissions exist by the time we enter; just wait for the validation
    # coordinator's next batch cycle to flip one to verified=true.
    deadline = time.monotonic() + 550
    while time.monotonic() < deadline:
        with db.cursor() as cur:
            cur.execute(
                "SELECT id FROM submissions WHERE verified = TRUE LIMIT 1"
            )
            if cur.fetchone():
                return
        time.sleep(5)

    # Conftest will attach a Postgres snapshot with the verified/error
    # breakdown — that tells us at a glance whether nothing came in, or
    # everything came in and got rejected.
    pytest.fail("no submission ever reached verified=TRUE within the deadline")
