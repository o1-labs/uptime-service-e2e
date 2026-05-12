package main

import (
	"os"

	"github.com/aws/aws-sdk-go-v2/aws"
	"github.com/aws/aws-sdk-go-v2/service/s3"
)

// S3OptionsFromEnv lets us point submission-updater at an S3-compatible server
// (MinIO in this e2e harness). Mirrors the same fix landed in
// uptime-service-backend. submission-updater pins aws-sdk-go-v2/config
// v1.26.0, which predates the SDK's native AWS_ENDPOINT_URL_S3 support
// (added in config v1.27, Feb 2024) — without this override the worker
// resolves the real AWS endpoint, gets back an empty block, and
// delegation-verify reports "Fail to decode block".
//
// Production deployments leave both env vars unset and fall back to AWS.
func S3OptionsFromEnv(o *s3.Options) {
	if endpoint := os.Getenv("AWS_ENDPOINT_URL_S3"); endpoint != "" {
		o.BaseEndpoint = aws.String(endpoint)
	}
	if os.Getenv("AWS_S3_FORCE_PATH_STYLE") == "1" {
		o.UsePathStyle = true
	}
}
