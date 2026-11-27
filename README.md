# NOEMA Orin

A dedicated workspace for running NOEMA **Controller processes** on a Jetson Orin Nano 8GB Developer Kit. The current release provides a synthetic, no-network Controller dry run, a pinned official-client proof against a **loopback fake server**, and read-only local host preflight. It does **not** deploy an agent fleet or connect to a live NOEMA world.

Hermes orchestration stays on its existing host. The NOEMA Gateway and World Engine retain world authority; this repository does not become a world writer.

## Current status

| Capability | Evidence and boundary |
| --- | --- |
| Hosted Controller dry run | Implemented with a scripted LOOK proposal and fake client. `ATTEMPTED` means a fake handoff, not world acceptance. |
| Official-client proof | Verified against loopback fake server (`SPEC-T4A.md`) and `noema-client` v0.2.0 granular `ClientPolicy` (`RFC-0141`). |
| Resident 6-agent system fleet (`m01`–`m06`) | Live Admin-minted system actors (`D-009`–`D-076`) with declarative `playbooks/`, `agenda.json` medium loop, shared `map.db` leases (`cohort_claims`), `RSI` canary ratchet, local `llama-server` System-1/System-2 routing, grounded voice verifier, and optional TensorRT FP16 hybrid memory. Excluded from live-agent censuses (`G-003`). |
| Local host preflight | Read-only, credential-free inspection (`python -m noema_orin.preflight`) with a bounded `SPECULATIVE` receipt (`SPEC-T5A.md`). |
| Physical Orin qualification | Opt-in harness implemented (`python -m noema_orin.qualify`, `jetson_telemetry.py`, `deploy/jetson/profile_nsys.sh`); `G-002` stays `NOT_COMPUTABLE` until on-board `OBSERVED` receipts are archived from the physical kit; see [#5](https://github.com/Zero-State-LLC/Noema-Orin/issues/5). |
| Live isolated-world attach / PSR-1 | External PSR-1 admission remains **blocked** (`G-003`); see [#4](https://github.com/Zero-State-LLC/Noema-Orin/issues/4). |
| Offline Spark Controller | **Blocked** by unresolved writer authority in Noema-Specs Spec 014 (`G-001`); see [#6](https://github.com/Zero-State-LLC/Noema-Orin/issues/6). |

The hosted and offline-research paths require separate world identities, endpoints, credentials, configuration profiles, and evidence. There is no automatic fallback between them. The Spark/Orin stack remains `SPECULATIVE` in [Noema-Specs](https://github.com/Zero-State-LLC/Noema-Specs/tree/619d0674518761aa08462d3f5d5966a917259aa1/specs/014-spark-orin-nvidia-stack); the source contract is pinned at `619d0674518761aa08462d3f5d5966a917259aa1`. A pin and local tests are not a live integration with the NOEMA runtime.

## Try the local foundation

Requires Python **3.10+**. From a checkout of this repository, on macOS or Linux:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install .
.venv/bin/python -m noema_orin --profile hosted --fixture fixtures/hosted-look.json --dry-run
.venv/bin/python -m noema_orin.preflight
```

On Windows, replace `.venv/bin/python` with `.venv\Scripts\python.exe`. Keep the checkout for the fixture: it is not included in the installed wheel. The dry run emits one `ATTEMPTED`/`FAKE_HANDOFF` JSON record from a fake client. The separate preflight command emits one `LOCAL_PREFLIGHT_ONLY`/`SPECULATIVE` record. It reads local host metadata; `NOT_COMPUTABLE` fields are intentionally not measurements. An exit code of zero from either command does **not** establish physical or live-world readiness.

To confirm the offline profile remains blocked, run the following **separately**; a nonzero exit is expected:

```sh
.venv/bin/python -m noema_orin --profile offline-spark --dry-run
```

It emits one `REFUSED`/`BLOCKED_SPEC_DEFECT` record. Never put credentials, private prompts, or production endpoints in fixtures, command lines, logs, or issues.

## Verify

From the checkout root:

```sh
PYTHONPATH=src .venv/bin/python -m unittest discover -s tests -q
```

The optional official-client loopback proof requires Python **3.11+** and the exact [client source pin](https://github.com/Zero-State-LLC/noema-client/tree/16ec5d1f472295055439975f88567a43fe6ee3b0). It is not part of the base install. Ubuntu x86_64 and arm64 CI validate packaging, synthetic behavior, and loopback behavior—not Jetson hardware or a live Gateway. For device preparation and installed-package checks, use the [Orin 8GB port packet](docs/ORIN-8GB-PORT.md).

## Source contracts

- [Controller-host scope and gates](SPEC.md)
- [Synthetic foundation](SPEC-FOUNDATION.md)
- [Official-client loopback proof](SPEC-T4A.md)
- [Local host preflight](SPEC-T5A.md)
- [Decisions and unresolved authority](DECISIONS.md)

No model, unattended service, production enrollment, Spark writer, or world cutover is authorized by these local proofs. Any live attach requires a separately authorized isolated world and scoped credentials; any offline writer change requires an accepted Noema-Specs decision.
