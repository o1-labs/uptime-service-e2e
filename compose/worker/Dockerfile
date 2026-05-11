# A thin wrapper that bakes our minimina-produced genesis ledger into the
# stock submission-updater image. The validation coordinator spawns this
# image as a worker per batch (via DinD); it can't push -v or -e flags we
# don't control, so the genesis path must live inside the image.
#
# submission-updater already reads GENESIS_LEDGER_FILE and forwards it as
# `--config-file` to the bundled mina-delegation-verify. Without a custom
# config the verifier validates against its compiled-in mainnet genesis,
# which never matches the synthetic genesis minimina spins up — every
# block would fail consensus checks.
ARG SUBMISSION_UPDATER_TAG=main-97163be
FROM ghcr.io/o1-labs/submission-updater:${SUBMISSION_UPDATER_TAG}

COPY genesis_ledger.json /etc/uptime-e2e/genesis_ledger.json
ENV GENESIS_LEDGER_FILE=/etc/uptime-e2e/genesis_ledger.json
