# NEXT: e2e audit (2026-11-23)

Verified this turn: 47 unit tests pass (py3.14, macOS arm64); hosted dry run emits ATTEMPTED/FAKE_HANDOFF; preflight emits LOCAL_PREFLIGHT_ONLY. Open gated issues: #4 live attach, #5 physical Orin, #6 offline Spark (all ready-for-human).

## Gaps
1. No cohort: runner is single Controller, single scripted LOOK. Nothing schedules N Controllers, budgets 8GB RAM per agent, or isolates per-agent credentials/receipts.
2. No real DecisionAdapter: only ScriptedAdapter. Noema-733/clients/noema-llm-agent exists but is not wired behind the port.
3. runner.run mixes validation of fixture, proposal and transport inline (shallow module). Extract Observation/Proposal parsers.
4. No console_scripts entry, fixture not packaged, version 0.0.1.
5. CI has no lint/type check (ruff, mypy/pyright) despite Protocol seams.
6. No FACTS.md.

## Recommended tickets (all credential-free, no live world)
- T7 Cohort dry run: `--cohort N` runs N synthetic Controllers with isolated identities and one receipt each, plus a cohort summary receipt.
- T8 Memory-budget gate in preflight: refuse cohort size whose estimated RSS exceeds the RAM bucket.
- T9 LLM adapter behind DecisionAdapter with a local stub model (no network), output validated by the same Proposal parser.
- T10 Refactor runner validation into deep parsers (no behavior change, existing tests are the guard).
- T11 Packaging/CI: entry point, packaged fixture, ruff + pyright job.
- Human gates unchanged: #5 needs the board, #4 needs an authorized isolated world, #6 needs Noema-Specs decision.

## Board session 2026-11-23 (OBSERVED via ssh orin)
- Device-tree: "NVIDIA Jetson Orin Nano Engineering Reference Developer Kit Super"; L4T R39.2.2; Ubuntu 24.04; Python 3.12.3; NV power mode MAXN_SUPER; NVMe 467G (316G free).
- RAM 7.3Gi total, 5.8Gi used, ~1.5Gi available: GNOME desktop, Firefox and a node process hold ~3.4GB. On-device inference is not viable until the board runs headless.
- On board: 59 tests pass; `--group 6` dry run gives ATTEMPTED 6/6; preflight now reports R39.2.2 / JETSON_ORIN_NANO_CANDIDATE after PR #23.
- Merged: #22 (T7 group dry run), #23 (preflight real-board labels).

## Next
1. Operator: decide whether to boot the Orin headless (`systemctl set-default multi-user.target`) to free ~3GB.
2. T9: wrap noema-llm-agent behind DecisionAdapter against LAN Ollama (qwen2.5:7b on the Mac), LOOK-only validation.
3. Expose Mac Ollama on LAN (OLLAMA_HOST=0.0.0.0) only when T9 needs it.
- Headless reboot done 2026-11-23: default.target=multi-user.target, gnome-shell not running, RAM available 1.5Gi -> 4.9Gi (2.4Gi used).
- T9 (PR pending): `ProposerAdapter` wraps any `propose(context)->str` such as `noema_llm_agent.llm.make_llm("ollama", model="qwen2.5:7b")`. OBSERVED on the Mac: 6-member group against local Ollama = ATTEMPTED 6/6 in 29.9s (~5s/decision, sequential). Orin->Mac LAN path not yet exercised (Ollama still bound to localhost).
- Upstream nit: noema-llm-agent protocol.py:457 has `return` in `finally` (SyntaxWarning on py3.14).

## 2026-11-24 memory/planner/stagger (D-013, PR #37)
- Live: 5/6 roles act in role (Founder office/agreement, QM harvest, Archivist reconstruct, Speaker message, Surveyor focus). Custodian still mostly inspect: no REPAIR offered nearby yet.
- Memory: per-agent `mind/memory.db`, shared `shared/map.db`, `shared/cohort.tsv` on Orin.
- OpenClaw gateway user unit stopped and disabled (operator-approved); free RAM 0.3 -> 1.2 GiB.
- Next: #34 confirm seating once agents co-locate with founder; #36 D1 replication; T15 metrics; clean up 12 duplicate Reach Compact orgs (founder can't dissolve; needs Admin decision).

## 2026-11-24 (later) seating + D1 mirror (D-014, PRs #39-#42)
- Agents now play as themed handles (stale resume tokens cleared).
- Reach Compact `org.reach-compact.34df3bb5`: founder Aphelia, member Cantor-Speaker, who holds office Notice (PUBLISH_NOTICE).
- Org commands needed ids from LOOK `target_id`/`cmd` (`_cmd_args`); founder no longer offers AGREEMENT_* (client gates it behind allow_contest).
- D1 mirror live: Worker `noema-orin-memory`, `noema-memory-sync.timer` every 5 min.
- RAM is tight again (~130-230 MiB free; llama-server ~5.8 GB). If OOM appears, raise turn-gap or move reflection to the Mac.
- Next: seat the remaining four (more office profiles), T15 metrics, Custodian/Archivist still mostly MOVE (routing finds no REPAIR/RECONSTRUCT rooms; inspect map.db offers).
