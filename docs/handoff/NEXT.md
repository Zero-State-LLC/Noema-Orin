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
