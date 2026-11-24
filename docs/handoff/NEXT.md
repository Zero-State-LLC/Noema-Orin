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
