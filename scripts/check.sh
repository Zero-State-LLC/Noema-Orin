#!/usr/bin/env bash
# Ship gate: exit nonzero on any test failure (D-045 shipped past a failing test via a grep gate).
# Runs twice: with noema-client (the live path) and without it (what CI's synthetic job sees).
set -euo pipefail
cd "$(dirname "$0")/.."
PYTHONPATH="src:${NOEMA_CLIENT_SRC:-$HOME/.jcode/scratch/wt/client/src}" python3 -m unittest discover -s tests -q
PYTHONPATH="src" python3 -m unittest discover -s tests -q
