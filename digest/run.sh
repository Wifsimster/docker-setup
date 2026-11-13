#!/bin/bash
set -euo pipefail
cd /opt/docker/digest
DATA="$(./collect.py)"
printf '%s' "${DATA}" | ./publish.py "$@"
