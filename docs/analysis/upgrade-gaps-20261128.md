# Noema-Orin upgrade and gap analysis (2026-11-28 03:05Z)

Evidence comes from the live Orin fleet (`metrics.db` digest, the last 1000 decision rows per agent, llama-server `/metrics`, unit files) and the repo at `4fb376a`. The clean window is the 2.5 h since the 00:18Z world recovery; 24 h figures include the 4.7 h INCIDENT.

> **Correction (2026-11-28 04:35Z).** Two findings below were wrong because the fleet's outcome labels were wrong. noema-client 0.2.0 marks a rejected WebSocket ACT_RESULT ok whenever it carries an observation, and the Worker attaches one to every rejection (noema-client#58). Checked against the next observation, 144 of 386 mutating turns logged as accepted had been refused.
> - **Item 2:** m05's fallback MESSAGEs were not reaching anyone. A MESSAGE affordance carries no text, so the engine refused each one ("Name a recipient and write a message."). That was 111 of 159 checked. The recipient list below is what m05 tried to send, not what was delivered. Fixed by D-085 (#222).
> - **Items 14 and 15:** "real rejection signal is sparse" and "shadow accuracy shows only tn" were artifacts of the same bug. Rejections were frequent but labelled ok. The turn log labels them correctly from #221, so re-measure before judging stage 2.

## Measured state

| Agent | Role | Role-action rate (2.5 h) | Idle rate | Decision sources (last ~340 turns) |
|---|---|---|---|---|
| m01 | founder | 0 / 146 | 100% | idle_skip 56%, loop_break 28%, fallback 16%, **model 0%** |
| m02 | quartermaster | 13 / 147 | 59% | planner 77%, loop_break 23% |
| m03 | custodian | 10 / 139 | 47% | planner 70%, loop_break 23%, model 3% |
| m04 | archivist | 2 / 144 | 92% | idle_skip 69%, loop_break 28%, model 4% |
| m05 | speaker | 9 / 164 | 34% | **fallback 68%**, loop_break 21%, planner 8%, model 3% |
| m06 | surveyor | 13 / 138 | 65% | model 47%, loop_break 20%, fallback 12%, planner 11% |

- In the last 3 h the six players made **0** Workers AI calls (cost table; maint made 109). Local inference decided 0–4% of turns on m01–m05 and 47% on m06, about 9% of fleet turns. Scripted logic decides the rest.
- llama-server holds **3.2 GB RSS** (8192 ctx, 2 slots), the largest process on an 8 GB board. Free RAM is about 2.0 GB.
- Loop-break fired on 12–27% of all turns. On m02, m03 and m06, 141–169 of the last 1000 loop-breaks came right after a productive HARVEST/REPAIR/REFINE.
- MOVE immediate reversals (east then west): m02 33%, m04 30%, m06 18% of moves. On m02 most are planner then planner (60 of 109), and 35 are loop-break then planner.
- m05 sent 379 MESSAGEs in 1000 turns, 363 of them from the generic fallback, with a median gap of **1 turn**. Top recipients: `player.tester` 198, `reach-maint3` 154, the org 118, and its own cohort (Perigee 115, Aphelia 97, Rivet 91).
- STALE_HEAD: about 1 per session per agent (26–45 per agent per 24 h). This is the server-side settlement race, Noema#983/#984.

## Gaps, ranked by impact

### P1: agent behaviour (where the fleet loses most turns)

1. **Loop-break punishes repeated productive work, and the planner oscillates.** `decide()` (orin_adapter.py, around L606) forces a MOVE whenever the last two `(action, target)` pairs equal the current one. HARVEST on the same cache three times running is the quartermaster's job, yet it triggers a walk east, then the planner walks back west (35 of m02's 109 reversals). The planner itself also oscillates between two rooms (60 of 109 are planner then planner), probably a route target that flips as stock or need changes. Fix: (a) exempt planner-sourced productive verbs (HARVEST/REPAIR/REFINE/CRAFT/SUPPLY) from loop-break while the last result shows progress (storage or stock changed), keeping the guard for WAIT, LOOK and INSPECT; (b) add hysteresis to the planner's route target, holding a chosen destination for N turns or until reached. Expected gain: about 15–20% of turns back to role work on m02, m03 and m06.
2. **m05 speaker spams MESSAGE through the fallback.** Of m05's last 1000 turns, 713 were `fallback`, and in every one of them ORG_OFFICE_ACT (its Notice office) was on offer. ORG_OFFICE_ACT is hidden for the speaker (`_hidden_verbs`, D-067, planner-only), and the speaker playbook (`playbooks/speaker.py`) only publishes a notice when a new fact exists. So the turn falls through to `_role_fallback`, which picks the first non-shared verb on offer, MESSAGE (375 of 713), bypassing `_social_outreach_ready()` because the cooldown only gates the model and playbook paths. Messaging its own cohort and the test account is noise in the public world. Fix: apply the social cooldown in `_role_fallback`, and drop cohort and `tester` recipients from the speaker's options.
3. **m01 founder and m04 archivist have nothing to do, and this is mostly Orin bugs, not role scope** (see `docs/research/open-decisions-20261128.md` Q1 and Q2). The founder sits at 100% WAIT/MOVE: its contract planner reads the org treasury, which the engine shows only to `OPERATE_RESOURCE_ACCOUNT` office holders, so every contract gate reads 0. Its governance and COMMEMORATE steps wait for menu rows the engine never emits. The archivist sits at 92% idle: its COMMEMORATE step has the same dead menu check, and it doesn't seek out rooms where new scars, crystallized lore or crime residues appear. All fixes are Orin-only.
4. **The model barely runs.** The players hit `planner`, `idle_skip` or `fallback` before `_ask()` in more than 90% of turns, so the local Qwen2.5-3B and the Workers AI budget go unused while behaviour stays scripted. If that's intended (determinism), reclaim the RAM (item 6). If not, route the fallback turns (m05's 68%) to `_ask()` first: local inference measured 0.74–1.3 s per choice just now.

### P2: platform and ops

5. **Production world incident handling.** The world sat in INCIDENT for 4.7 h. The digest only showed "sessions ended early" until #214. Root-cause fix: Noema#984 (awaiting code-owner review, then the production deploy). Still missing: no push alert when a crit alert fires, and the dashboard alone isn't watched overnight. The Orin's Signal REST container (`signal-daemon`) is unhealthy and returns 404, so email through the AgentMail account `admin_login.py` already uses is the cheaper channel (see `docs/research/open-decisions-20261128.md`, O3).
6. **llama-server memory.** RSS 3.2 GB plus 3.1 GB in swap (anonymous KV and compute buffers paged out while idle; the GGUF itself is 1.9 GB), for a model that decides about 9% of fleet turns (mostly m06). Options: `--ctx-size 4096 -np 1` (about 0.6–0.8 GB less KV cache; there are no concurrent requests, since `n_busy_slots_per_decode` is 1.0), or socket-activate it. Ollama still runs as a second runtime (enabled; 29 MB idle, no model loaded). It isn't fully redundant: `from_env()` defaults `NOEMA_LLM_BASE` to Ollama `:11434`, and `_chat`'s last fallback posts there. Point `NOEMA_LLM_BASE` at llama-server `:8081` and the last fallback uses the same server, then Ollama can be disabled. The cost alarm counts that path as "Ollama fallbacks" (37% over 24 h, inflated by the incident).
7. **No log rotation.** `StandardOutput=append:` logs have grown since 11-24 (1.9–2.2 MB per agent, about 0.6 MB per day per agent). There's no logrotate rule and `journalctl --user` has no journal. Not urgent (311 GB free), but add a `copytruncate` logrotate entry or size-capped rotation in the supervisor before the logs reach hundreds of MB and slow the metrics tailer.
8. **Token expiry is 26 days out (about 12-24).** `noema-token-watch.timer` exists, but re-minting needs an Admin login (`admin_login.py`, email magic link). Automate it: a 7-day-before re-mint job on the Mac (where the admin login lives) that runs `admin_login.py` and then `deploy/remint-tokens.py --apply`.
9. **Partial backup of agent minds.** `~/noema-players/m0*/mind` is 8–22 MB per agent. Memory-sync pushes new memories, persona versions and the digest to the cloud D1, but not the transition logs (D-078/D-079 training data), RSI knobs or agenda. Those exist only on the Orin's NVMe. A nightly `rsync` of `mind/` (rotated `.gz` segments plus knobs) to the Mac or to R2 closes this.

### P3: code health

10. **`orin_adapter.py` is 1324 lines** and `decide()` is 195 lines of interleaved guards (planner, idle_skip, ask, fallback, D-066 gate, loop-break, records). Phase 2 (T8) playbooks exist for all six roles (`playbooks/`, 623 lines; the custodian's is 15 lines and the surveyor's 21), but the cross-cutting guards (loop-break, idle_skip, fallback, social cooldown) still live in `decide()`. Each D-0xx fix lands there. Moving those guards behind a per-role policy, with tests per role, would make items 1–3 one-file changes.
11. **The test matrix skips the code that runs in production.** The CI synthetic job runs 6 OS/Python combinations, but 52 tests skip without `noema-client`, including `test_transitions.DecideHookTests` and `test_consequence.DecideShadowTests`, which exercise the production decide path. Production runs noema-client 0.2.0 on Python 3.12. Add one CI job that installs the pinned client (0.2.0, `89a1fcac`) so those 52 run.
12. **Stale pins.** `official_client.py` (T4a loopback proof) and `tests_optional` still accept only 0.1.23/0.1.24. CI checks out `16ec5d1` for the optional job, while production and `official_isolated.py` use 0.2.0.
13. **The execplan is stale.** `execplan/03` still has T14 unchecked ("awaiting physical execution"), although #168 and #5 closed with an OBSERVED receipt.

### P4: research upgrades (gated on data)

14. **Consequence model stage 2 (veto).** Waiting for a clean day under #215. Note that most rejections the fleet now sees are STALE_HEAD (race) and `ACTION_REJECTED` on `?` (no proposal), neither of which a veto can prevent. Measure the preventable share before building stage 2.
15. **Shadow accuracy per verb shows only tn.** Real rejection signal is sparse (about 1–2 per session). At this rate tp/fp support for any (action, context) key takes days. Consider logging INVALID_PROPOSAL and BUDGET_EXCEEDED pre-flight blocks (the `blocked` list, for example 457 CRAFT "lack regional material" on m03) as labelled negatives. They're free, deterministic labels.

## Suggested order

1. Items 1 and 2 (loop-break exemption, speaker cooldown): small, testable, and they recover the most turns. Canary m02 and m05.
2. Item 6 (llama ctx/np and disabling Ollama), plus item 7 (logrotate): ops, a few minutes each, measurable as freed RAM.
3. Item 11 (CI job with the pinned client) and items 12–13 (pins, execplan).
4. Item 5 (email push for crit alerts) and items 8–9 (token re-mint automation, mind backups).
5. Item 3 (founder treasury view and direct governance and COMMEMORATE proposals, archivist routing): Orin-only, canary m01 and m04.
6. Item 10 (playbook decomposition), incrementally as roles are touched.
