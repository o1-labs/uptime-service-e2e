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


@pytest.mark.timeout(1200)
def test_minimina_submissions_get_verified(backend_ready, db):
    deadline = time.monotonic() + 1150
    last = None
    while time.monotonic() < deadline:
        with db.cursor() as cur:
            cur.execute(
                "SELECT submitter, block_hash, state_hash, verified, validation_error "
                "FROM submissions WHERE verified = TRUE LIMIT 1"
            )
            verified_row = cur.fetchone()
            if verified_row:
                return
            # Capture the latest attempt for debugging on timeout.
            cur.execute(
                "SELECT submitter, verified, validation_error FROM submissions "
                "ORDER BY id DESC LIMIT 1"
            )
            last = cur.fetchone()
            if last and last[2]:  # validation_error set → fail fast
                pytest.fail(
                    f"validation rejected a block: submitter={last[0]}, "
                    f"error={last[2]!r}"
                )
        time.sleep(5)

    pytest.fail(
        f"no submission reached verified=true within the deadline; "
        f"last row: {last}"
    )
