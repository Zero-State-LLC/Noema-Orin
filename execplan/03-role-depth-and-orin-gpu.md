# 6-Agent Role Depth, Rejection Zeroing, and Jetson Orin Nano GPU Roadmap (`D-076`)

This ExecPlan is a living document tracking the three-phase upgrade roadmap authorized by operator decision `D-076` (2026-11-27) and published under parent [Spec #154](https://github.com/Zero-State-LLC/Noema-Orin/issues/154).

## Purpose / Big Picture

Complete the accepted `RFC-0138`, `RFC-0141`, and `RFC-0144` resident fleet capabilities on `Noema-Orin`, eliminate the predictable rejection tax observed in `docs/metrics/fleet-20261126T2340Z.json`, and stage the move from cloud-first index picking to local-first Jetson Orin Nano GPU inference (`llama-server` CUDA with JSON-schema grammar) plus physical Orin qualification (`#5` / `G-002`).

All constitutional boundaries remain intact:
- Controller acts strictly through `noema-client` `ActionProposal`s over `/v1/command`; never a world writer.
- Private cognition (`persona.json`, `policy_knobs.json`, `agenda.json`, `memory.db`, `shared/map.db`) stays off-wire (`ADR-0002`).
- `DENY_ALWAYS` and `_hidden_verbs()` (`SUPPLY`, `CONTRACT_POST`, `SANCTION`, `TRADE`) remain permanently enforced.
- `G-001` (`offline-spark`) and `G-003` (`PSR-1`) remain blocked; `preflight.py` (`SPEC-T5A`) stays unchanged.

## Progress

- [x] (2026-11-27) Operator approved 3-phase plan, Phase 1 `ready-for-agent` gating (`T1`–`T7`), Phases 2–3 `ready-for-human` gating (`T8`–`T14`), and `llama-server` target for `T10` (`D-076`).
- [x] (2026-11-27) Published parent [Spec #154](https://github.com/Zero-State-LLC/Noema-Orin/issues/154) and child tickets `#155`–`#168` (`T1`–`T14`) with native sub-issue links and blocking edges.
- [x] (2026-11-27) `T1` (#155): Dual-track `FOCUS` (`ACTIVE_FOCUS_CAP = 2`) and role focus targets.
- [x] (2026-11-27) `T2` (#156): Shared map `cohort_claims` lease table and cross-cohort damaged-infra work queue.
- [x] (2026-11-27) `T3` (#157): Pre-flight precondition mirroring and `STALE_HEAD` phase jitter + digest tracking.
- [x] (2026-11-27) `T4` (#158): `m02` complete storefront (`SELL_OFFER`, `CORE_SWAP`, `SALVAGE_COMPOSITE` `BUY_ORDER`).
- [x] (2026-11-27) `T5` (#159): `m01` full civic contracts (4 kinds), `OPEN_CHARTER`, `COMMEMORATE`, and colocated diplomacy.
- [x] (2026-11-27) `T6` (#160): `m03` fleet-aware crafting, `m04` state-delta supersession, and `m05` grounded market/contract Herald digests.
- [x] (2026-11-27) `T7` (#161): Wire dead RSI knobs, persona traits, Deep Time epoch reversion, and `reflect()` prompt knobs.
- [x] (2026-11-27) `T8` (#162): Declarative `playbooks/` state machines (`founder`, `quartermaster`, `custodian`, `archivist`, `speaker`, `surveyor`, `common`).
- [x] (2026-11-27) `T9` (#163): Medium-loop `agenda.json` planner (`AgendaManager`, 3–5 typed sub-goals surviving session restarts).
- [x] (2026-11-27) `T10` (#164): Local CUDA `llama-server` backend (`llm_client.py`), constrained JSON-schema grammar, `NOEMA_INFERENCE_MODE=local_first` routing, `local_s1_calls` health tracking, and `deploy/jetson/noema-llama-server.service`.
- [x] (2026-11-27) `T11` (#165): Grounded character voice synthesis (`voice.py`) with deterministic seq/number/privacy verifier and template fallback.
- [ ] `T12`–`T14` (#166–#168): Phase 3 (TensorRT `bge-small`, Tegra telemetry, `#5` physical Orin qualification).

## Ticket Graph & Blocking Edges

| Ticket | Issue | Label | Blocked By | Scope |
|---|---|---|---|---|
| `T1` | [#155](https://github.com/Zero-State-LLC/Noema-Orin/issues/155) | `ready-for-agent` | — | Dual-track `FOCUS` (`RFC-0144 §1`) |
| `T2` | [#156](https://github.com/Zero-State-LLC/Noema-Orin/issues/156) | `ready-for-agent` | — | `cohort_claims` & shared damaged-infra `shared_work` |
| `T3` | [#157](https://github.com/Zero-State-LLC/Noema-Orin/issues/157) | `ready-for-agent` | — | Pre-flight resource/policy/colocation guards & `STALE_HEAD` jitter |
| `T4` | [#158](https://github.com/Zero-State-LLC/Noema-Orin/issues/158) | `ready-for-agent` | `#156`, `#157` | `m02` `SELL_OFFER`, `CORE_SWAP`, `SALVAGE_COMPOSITE` `BUY_ORDER` |
| `T5` | [#159](https://github.com/Zero-State-LLC/Noema-Orin/issues/159) | `ready-for-agent` | `#156`, `#157` | `m01` 4 contract kinds, `OPEN_CHARTER`, `COMMEMORATE`, colocated diplomacy |
| `T6` | [#160](https://github.com/Zero-State-LLC/Noema-Orin/issues/160) | `ready-for-agent` | `#155`–`#159` | `m03` fleet crafting, `m04` delta supersede, `m05` Herald digests |
| `T7` | [#161](https://github.com/Zero-State-LLC/Noema-Orin/issues/161) | `ready-for-agent` | — | Wire dead RSI knobs, persona traits, epoch reversion, `reflect()` prompt |
| `T8` | [#162](https://github.com/Zero-State-LLC/Noema-Orin/issues/162) | `ready-for-human` | `#160`, `#161` | Decompose `orin_adapter.py` into `playbooks/` |
| `T9` | [#163](https://github.com/Zero-State-LLC/Noema-Orin/issues/163) | `ready-for-human` | `#162` | Medium-loop `agenda.json` planner |
| `T10` | [#164](https://github.com/Zero-State-LLC/Noema-Orin/issues/164) | `ready-for-human` | `#162` | Local CUDA `llama-server` + JSON-schema grammar + S1/S2 routing |
| `T11` | [#165](https://github.com/Zero-State-LLC/Noema-Orin/issues/165) | `ready-for-human` | `#163`, `#164` | Grounded character voice synthesis + verifier |
| `T12` | [#166](https://github.com/Zero-State-LLC/Noema-Orin/issues/166) | `ready-for-human` | `#164` | TensorRT FP16 `bge-small` + hybrid recall |
| `T13` | [#167](https://github.com/Zero-State-LLC/Noema-Orin/issues/167) | `ready-for-human` | `#164` | Tegra/INA3221 telemetry + cgroup/NVMe hardening |
| `T14` | [#168](https://github.com/Zero-State-LLC/Noema-Orin/issues/168) | `ready-for-human` | `#166`, `#167` | Physical Orin qualification (`#5`), `nsys`, `README.md` sync |

## Validation and Acceptance

Phase 1 (`T1`–`T7`) is complete locally when:
1. Failing tests are written first for each slice and pass with `NOEMA_CLIENT_SRC=/home/myslef/projects/noema-suite/noema-client/src bash scripts/check.sh` (both with `noema-client` and without it).
2. `python3 .agents/machine.py check` and `git diff --check` exit zero.
3. No `DENY_ALWAYS` or `_hidden_verbs()` regression is introduced, and `preflight.py` / `offline-spark` remain untouched.
