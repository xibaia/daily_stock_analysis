#!/usr/bin/env bash
set -euo pipefail

cd /workspace/vendor/DeepEar

mkdir -p data reports

exec "$@"
