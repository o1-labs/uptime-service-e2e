# Two responsibilities in this image:
#
# 1) Bake our minimina genesis into a known path + expose it via
#    GENESIS_LEDGER_FILE so the bundled mina-delegation-verify gets
#    `--config-file <our genesis>` (otherwise it validates against its
#    compile-time mainnet genesis and rejects every block).
#
# 2) Replace the stock `submission_updater` Go binary with one patched
#    to honor AWS_ENDPOINT_URL_S3. The upstream binary uses
#    aws-sdk-go-v2/config v1.26.0, which doesn't read the env var; against
#    MinIO it tries the real AWS endpoint, downloads nothing, and the
#    verifier prints "Fail to decode block" for every submission.
#    See compose/worker/s3_options.go for the fix; this mirrors the
#    same patch landed in uptime-service-backend.

ARG SUBMISSION_UPDATER_TAG=main-97163be
# Same commit the bundled delegation-verify is from — must match the
# binary in the runtime image to keep linker symbols/aws-sdk versions
# aligned.
ARG SUBMISSION_UPDATER_COMMIT=97163be

# Stage 1 — build the patched submission_updater binary.
FROM golang:1.22-bullseye AS builder
ARG SUBMISSION_UPDATER_COMMIT
RUN apt-get update && apt-get install -y --no-install-recommends git ca-certificates \
    && rm -rf /var/lib/apt/lists/*
RUN git clone --depth 50 https://github.com/o1-labs/submission-updater.git /src \
    && cd /src && git checkout "${SUBMISSION_UPDATER_COMMIT}"
WORKDIR /src/src
# Drop in the S3 options override + wire it into the existing s3.NewFromConfig call.
COPY s3_options.go ./s3_options.go
RUN sed -i 's|s3\.NewFromConfig(awsCfg)|s3.NewFromConfig(awsCfg, S3OptionsFromEnv)|' s3.go
RUN go build -o /out/submission_updater .

# Stage 2 — runtime: the upstream image has everything else (delegation-verify,
# OpenSSL 1.1, awscli, etc.). We just swap the Go binary and add our genesis.
FROM ghcr.io/o1-labs/submission-updater:${SUBMISSION_UPDATER_TAG}
COPY --from=builder /out/submission_updater /go/bin/submission_updater
COPY genesis_ledger.json /etc/uptime-e2e/genesis_ledger.json
ENV GENESIS_LEDGER_FILE=/etc/uptime-e2e/genesis_ledger.json
