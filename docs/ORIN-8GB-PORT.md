# Jetson Orin Nano 8GB Controller-host port packet

**Scope:** NOEMA Controller processes only. Hermes orchestration remains on its existing host. This packet prepares a portable synthetic dry-run; it is not proof of execution on NVIDIA hardware, a live Gateway, or an offline Spark chamber.

## Authority and readiness

- Foundation PR #9 merged at `b6bb91c1d0be1ee48c009c746fb0767bb631bf79`. The official client integration (#4), physical measurement (#5), and offline Spark (#6) remain open.
- `hosted` is a fake-client dry-run only. Do not enroll a Player, copy a credential, invoke a production endpoint, or run `/play` browser automation from this packet.
- The Spark world-writer contradiction is unresolved in Noema-Specs Spec 014. `offline-spark` must remain a refusal. The operator alone decides any canonical change.
- No model has been selected. Exact installed client release, model license, and device configuration are unverified until observed on the returned Jetson Orin Nano 8GB Developer Kit. The official client source pin below is a **read-only API reference**, not an installed or connected client.

## Pre-device portable artifact

The current synthetic package declares Python >=3.10, has no official-client dependency, and produces a pure-Python wheel. CI covers Ubuntu x86_64 Python 3.10–3.13 and Ubuntu 24.04 arm64 Python 3.10 and 3.12. These are architecture/packaging checks, **not** JetPack or device evidence. Do not install CUDA, TensorRT, Cosmos, or hosted credentials just to run the foundation. The receipt's `source_sha` is the pinned **Noema-Specs** commit `619d0674518761aa08462d3f5d5966a917259aa1`, not this repository's commit; record the latter separately during installation.

| Published platform path (not tested on this board) | OS and default Python | Foundation / future client constraint |
| --- | --- | --- |
| [JetPack 7.2.1 / L4T 39.2.1](https://docs.nvidia.com/jetson/orin-nano-devkit/user-guide/latest/quick_start.html) | Ubuntu 24.04 aarch64 / Python 3.12 | Foundation installable by declared floor; official-client integration still gated. |
| [JetPack 6.2.3 / L4T 36.5.2](https://docs.nvidia.com/jetson/archives/r36.5.2/ReleaseNotes/Jetson_Linux_Release_Notes_r36.5.2.pdf) | Ubuntu 22.04 aarch64 / Python 3.10 | Foundation can run on the default Python; `noema-client` v0.1.23 requires Python >=3.11, so #4 would require a separately provisioned compatible interpreter or a different verified client release. |

Before installing an OS, check the board's QSPI/UEFI firmware. JetPack 7.2.1 requires the [JetPack 6.x firmware update path](https://docs.nvidia.com/jetson/orin-nano-devkit/user-guide/latest/update_firmware.html) on older kits. For JetPack 7.2.1, write the **Jetson ISO to USB**, then install to microSD or NVMe; NVIDIA says not to flash the ISO to microSD as an SD-card image. Do not choose an image until the actual board and target storage are inspected.

The official [`noema-client` v0.1.23 at `16ec5d1f472295055439975f88567a43fe6ee3b0`](https://github.com/Zero-State-LLC/noema-client/tree/16ec5d1f472295055439975f88567a43fe6ee3b0) exposes `NoemaClient.discover()`, `connect()`, `observe()`, `act(ActionProposal)`, `play()` and `close()`, plus an injectable `http` transport. There is **no public `submit(mapping)`**. The opt-in T4a adapter translates the already validated LOOK proposal into a public `ActionProposal` on Python >=3.11; it refuses non-loopback origins and inherited credential selectors; the opt-in tests prepare it only against the pinned client's fake HTTP server. This proof does **not** add the official client as a mandatory dependency or change the Python >=3.10 synthetic CLI. To reproduce it from a pinned Noema-Orin checkout with a Python >=3.11 environment, clone `Zero-State-LLC/noema-client` at the exact SHA above into a temporary sibling directory, install both checkouts into a clean venv, then from **outside** the Orin checkout run `PYTHONPATH=<absolute-client-checkout>/tests <venv-python> -m unittest discover -s <absolute-orin-checkout>/tests_optional -p test_official_client.py -v` with `PYTHONHOME`, `NOEMA_TOKEN`, `NOEMA_SERVER`, `NOEMA_CONFIG_DIR`, `NOEMA_WORLD_ID`, `NOEMA_ADMIN_TOKEN`, and `XDG_CONFIG_HOME` unset. The fake server binds `127.0.0.1` on an ephemeral port, generates only fixture tokens, and sends `ENTER_WORLD`, `OBSERVE`, `LOOK` in the successful case. CI runs this in separate Python >=3.11 jobs, never in the synthetic Python 3.10 job. The official client may retry an HTTP transport error internally; the Orin runner makes only one submission at its own seam. Neither attempt proves world acceptance or live-client admission. #4 still needs separate authorization, a scoped Controller credential, human enrollment and signed Admin JWT before any real isolated attach. The operator proof script is not part of this packet.

On a clean host with Python 3.10 or newer, first check out the **reviewed exact Noema-Orin commit** and keep that checkout: `fixtures/hosted-look.json` is a tracked, non-secret test fixture, **not** wheel package data. From that checkout root:

    python3 -m venv .venv
    .venv/bin/python -m pip install --upgrade pip
    .venv/bin/python -m pip install .
    .venv/bin/python -m noema_orin --profile hosted --fixture fixtures/hosted-look.json --dry-run
    .venv/bin/python -m noema_orin --profile offline-spark --dry-run

The hosted command emits one `ATTEMPTED`/`FAKE_HANDOFF` record (exit 0); this is a fake submission, not world acceptance. The offline command emits one `REFUSED`/`BLOCKED_SPEC_DEFECT` record (exit 1). Run commands separately; do not turn a refusal's nonzero exit into a false install failure. Never put secrets in fixtures, CLI args, screenshots, logs, or issues. Re-run the full suite from the source checkout with `PYTHONPATH=src .venv/bin/python -m unittest discover -s tests -q` if testing from a checkout. Windows uses `.venv\Scripts\python.exe` instead of `.venv/bin/python`.

## Day-one device acceptance (not yet performed)

1. Obtain the returned board and confirm it is the expected 8GB kit; record board identifier, QSPI/UEFI firmware, JetPack/L4T and Ubuntu releases (`cat /etc/os-release`, `cat /etc/nv_tegra_release` when present), architecture (`uname -m`), Python version (`python3 --version`), storage and available memory, power supply/mode, network route, and Orin repo Git commit separately from the Specs source pin. Do not store a MAC address, serial, credential, or private endpoint in a public receipt.
2. Install from that pinned checkout, or install its reviewed wheel while retaining the matching pinned checkout for the fixture. Use an unprivileged local account. Repeat the two CLI commands above from the checkout root, then run the installed CLI from outside the checkout with the fixture's absolute path to verify packaging rather than source-tree import. Record stdout, stderr, exit codes, and import path. If package install fails, stop; do not silently switch to a source-tree `PYTHONPATH` pass.
3. Collect idle and loaded memory/power samples with approved on-device tools (for example `tegrastats` and `nvpmodel`) only after confirming their installed versions. Do not claim tokens/s or latency without a chosen licensed model and a measured workload; absent values stay `NOT_COMPUTABLE`.
4. Stop before #4 official-client integration or any hosted attach. A separately authorized isolated world, actual first-party client API/version, human enrollment, discovery/seal, scoped credential and operator stop are prerequisites for that stage. No unattended service or boot-autostart is included in this packet.
5. Resolve #6 in Noema-Specs through an accepted canonical decision explicitly scoping a separate offline chamber and its identity/evidence boundary. Neither this repo nor a device receipt can make Spark the hosted world writer.

## Recovery

To remove the dry-run install, deactivate the virtual environment and delete only the local `.venv` created for this checkout. Keep profile-specific credentials out of this repo. A changed source SHA or official-client version invalidates old compatibility evidence; rerun acceptance on the new exact commit. Mark missing device readings `NOT_COMPUTABLE`, not passed.
