#!/usr/bin/env bash
# Capture NVIDIA Nsight Systems timeline across Orin agent decision stages (T14/#168).
set -euo pipefail

OUT="${1:-/tmp/noema-orin-profile}"
export NOEMA_NVTX=1

nsys profile \
  --trace=cuda,nvtx,osrt \
  --stats=true \
  --output="$OUT" \
  python3 -m noema_orin.qualify
