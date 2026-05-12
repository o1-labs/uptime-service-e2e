# Custom worker that pairs the patched `submission_updater` orchestrator
# (Go) with a `mina-delegation-verify` binary that matches the mina-daemon
# our minimina topology runs. submission-updater's stock image bundles a
# delegation-verify built from MINA_BRANCH=berkeley DUNE_PROFILE=mainnet —
# that mismatches the testnet-sig devnet daemon, so Pickles.verify fails
# every dlog_check. The mina-delegation-verifier image from the same commit
# as the daemon (4345f4c, compatible branch, devnet profile) has the right
# pickles SRS + verification keys baked in.

ARG SUBMISSION_UPDATER_COMMIT=97163be
# Verifier image built from the same Mina commit as the daemon node in
# fixtures/minimina/topology.json. Both must move together.
ARG VERIFIER_IMAGE=europe-west3-docker.pkg.dev/o1labs-192920/euro-docker-repo/mina-delegation-verifier:4345f4c-bookworm-devnet

# Stage 1 — build the patched submission_updater Go binary.
# Static build keeps it portable across the bullseye/bookworm split between
# submission-updater's original image and the bookworm-based verifier
# image we use as runtime here.
FROM golang:1.22-bookworm AS builder
ARG SUBMISSION_UPDATER_COMMIT
RUN apt-get update && apt-get install -y --no-install-recommends git ca-certificates \
    && rm -rf /var/lib/apt/lists/*
RUN git clone --depth 50 https://github.com/o1-labs/submission-updater.git /src \
    && cd /src && git checkout "${SUBMISSION_UPDATER_COMMIT}"
WORKDIR /src/src
COPY s3_options.go ./s3_options.go
# Wire the env-driven options into the existing s3.NewFromConfig call so
# submission-updater honors AWS_ENDPOINT_URL_S3 / AWS_S3_FORCE_PATH_STYLE
# against MinIO. Mirrors uptime-service-backend's fix.
RUN sed -i 's|s3\.NewFromConfig(awsCfg)|s3.NewFromConfig(awsCfg, S3OptionsFromEnv)|' s3.go
RUN CGO_ENABLED=0 go build -o /out/submission_updater .

# Stage 2 — runtime: use the matching verifier image so the bundled
# mina-delegation-verify already has the correct verification keys.
FROM ${VERIFIER_IMAGE}
COPY --from=builder /out/submission_updater /usr/local/bin/submission_updater
COPY genesis_ledger.json /etc/uptime-e2e/genesis_ledger.json
ENV GENESIS_LEDGER_FILE=/etc/uptime-e2e/genesis_ledger.json
ENV DELEGATION_VERIFY_BIN_PATH=/usr/local/bin/mina-delegation-verify
# Override the verifier image's ENTRYPOINT (which is mina-delegation-verify
# directly); the validation coordinator runs the worker like
# `docker run <image> <batch_start> <batch_end>`, which submission_updater
# parses as positional args.
ENTRYPOINT ["submission_updater"]
