# Jetson Orin Nano 8GB Controller-host port packet

**Scope:** NOEMA Controller processes only. Hermes orchestration remains on its existing host. This packet prepares a portable synthetic dry-run; it is not proof of execution on NVIDIA hardware, a live Gateway, or an offline Spark chamber.

## Authority and readiness

- Foundation PR #9 merged at `b6bb91c1d0be1ee48c009c746fb0767bb631bf79`. The official client integration (#4), physical measurement (#5), and offline Spark (#6) remain open.
- `hosted` is a fake-client dry-run only. Do not enroll a Player, copy a credential, invoke a production endpoint, or run `/play` browser automation from this packet.
- The Spark world-writer contradiction is unresolved in Noema-Specs Spec 014. `offline-spark` must remain a refusal. The operator alone decides any canonical change.
- No model has been selected. The user's target is a Jetson Orin Nano **8GB Developer Kit**; exact board revision, firmware, JetPack/L4T, storage, power mode, network, Python, official client pin, and model license are unverified until observed on the returned device.

## Pre-device portable artifact

The package declares Python >=3.10. CI covers Ubuntu x86_64 Python 3.10–3.13 and Ubuntu arm64 Python 3.10. These jobs are architecture/packaging evidence only, not JetPack or device evidence. Use the repository's Python 3.10-compatible pure-Python wheel; do not install CUDA, TensorRT, Cosmos, or hosted credentials just to run the foundation. The receipt's `source_sha` is the pinned **Noema-Specs** commit `619d0674518761aa08462d3f5d5966a917259aa1`, not this repository's commit; record the latter separately during installation.

On a clean host with Python 3.10 or newer, from the repo root:

    python3 -m venv .venv
    .venv/bin/python -m pip install --upgrade pip
    .venv/bin/python -m pip install .
    .venv/bin/python -m noema_orin --profile hosted --fixture fixtures/hosted-look.json --dry-run
    .venv/bin/python -m noema_orin --profile offline-spark --dry-run

The hosted command emits one `ATTEMPTED`/`FAKE_HANDOFF` record (exit 0); this is a fake submission, not world acceptance. The offline command emits one `REFUSED`/`BLOCKED_SPEC_DEFECT` record (exit 1). Run commands separately; do not turn a refusal's nonzero exit into a false install failure. Never put secrets in fixtures, CLI args, screenshots, logs, or issues. Re-run the full suite from the source checkout with `PYTHONPATH=src .venv/bin/python -m unittest discover -s tests -q` if testing from a checkout. Windows uses `.venv\Scripts\python.exe` instead of `.venv/bin/python`.

## Day-one device acceptance (not yet performed)

1. Obtain the returned board and confirm it is the expected 8GB kit; record board identifier, JetPack/L4T and Ubuntu releases, architecture, Python version, storage and available memory, power supply/mode, network route, and source SHA. Do not store a MAC address, serial, credential, or private endpoint in a public receipt.
2. Install from a pinned Git commit or reviewed wheel using an unprivileged local account. Repeat the two CLI commands above offline. Record stdout, stderr, exit codes, and import path. If package install fails, stop; do not silently switch to a source-tree `PYTHONPATH` pass.
3. Collect idle and loaded memory/power samples with approved on-device tools (for example `tegrastats` and `nvpmodel`) only after confirming their installed versions. Do not claim tokens/s or latency without a chosen licensed model and a measured workload; absent values stay `NOT_COMPUTABLE`.
4. Stop before #4 official-client integration or any hosted attach. A separately authorized isolated world, actual first-party client API/version, human enrollment, discovery/seal, scoped credential and operator stop are prerequisites for that stage. No unattended service or boot-autostart is included in this packet.
5. Resolve #6 in Noema-Specs through an accepted canonical decision explicitly scoping a separate offline chamber and its identity/evidence boundary. Neither this repo nor a device receipt can make Spark the hosted world writer.

## Recovery

To remove the dry-run install, deactivate the virtual environment and delete only the local `.venv` created for this checkout. Keep profile-specific credentials out of this repo. A changed source SHA or official-client version invalidates old compatibility evidence; rerun acceptance on the new exact commit. Mark missing device readings `NOT_COMPUTABLE`, not passed.
