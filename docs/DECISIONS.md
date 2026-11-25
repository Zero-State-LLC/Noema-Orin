
## D-030 Depleted agents WAIT, and the decide model is picked by tier

- **Energy.** Engine #910/#911 (merged and live 2026-11-25) extends RFC-0117 lockout rest to energy 0 with an empty hold. The planner and the loop-breaker now WAIT whenever energy is 0. Before this, m06 looped FOCUS/LOOK at energy 0 and never got the rest.
- **Model tier.** Each turn's menu gets a tier. If every option is routine and reversible (LOOK/WAIT/MOVE/HARVEST/REPAIR/FOCUS/RESTORE and the COMMIT.* forms), the Worker uses `CHEAP_DECIDE_MODEL`, default `@cf/ibm-granite/granite-4.0-h-micro` at $0.017/M in (about 16x cheaper; returned correct JSON 3/3 on a probe, Gemma 4 returned empty text; llama-3.1-8b-fp8 was deprecated 2026-11-20). The Worker falls back to strong on any cheap-model error. If any social, org or build verb is offered, it keeps Scout at $0.27/M in. The verb verdicts came from `jev route-to` (scripts/jev_tier.sh) and are frozen in `model_tier.CHEAP`, so there's no Jev call per turn. Jev picks below 0.7 confidence went to strong. llama-3.2-3b was skipped: deprecation was scheduled for 2026-11-20.

## D-031 Retarget office creates before the planner dedup

After Notice existed, `planner.refine` dropped the engine's only create option (`name="Notice"`) as a duplicate before `offices.retarget_create` could rewrite it to Steward or Archive Keeper. So the founder was never offered the missing offices. `_menu` now retargets first. Regression: `tests/test_offices.py::MenuPipelineTests`.

## D-032 Harvest in bulk

The engine's HARVEST affordance always says `amount 1`. HARVEST costs a flat 2 energy, and WAIT turns 1 cargo into 2 energy, so harvesting one unit at a time only breaks even. m02 cycled HARVEST/WAIT at energy 1 to 3 for hours. The adapter now sets amount = min(8, free storage, visible stock). One harvest then fuels several WAITs (+2 energy each) and gives materials for repair and build. Holding 8 cargo costs +1 per MOVE, which one WAIT more than covers.

**D-032 correction (live, 2026-11-25 03:10Z).** Energy doesn't improve. WAIT refuels a flat +2 per WAIT whatever the cargo, and m02's hold was already full, so steady state stays at about one WAIT per 2-energy action. Bulk harvest still fills empty holds faster (custodian supply for REPAIR/CONSTRUCT), so it stays. The role-action ceiling of about 50% for energy-spending roles is an engine economy property (RFC-0117/0119), not an adapter bug. Raising it means an engine rule change (operator decision).

## D-033 Don't WAIT for energy that WAIT can't give

At energy 1 with an empty hold, engine WAIT restores nothing: lockout rest needs energy 0, and cargo fuel needs cargo. The planner still WAITed "for energy" there, then the loop-breaker MOVEd, so the custodian spent about 50% of its turns on no-op WAITs and never reached a role action. `_starved_for_attention` now counts energy only when WAIT actually refuels.

## D-034 Walk toward the goal when WAIT can't refuel

At energy 1 with an empty hold and no role verb here, the planner now spends the 1 energy MOVEing toward the goal room. It arrives at 0 and gets lockout rest (+2) there. Before this, the loop-breaker sent it the wrong way. That still leaves the in-room case: at energy 1 in the harvest room, HARVEST needs 2, and nothing burns 1 without leaving. The proper fix is an engine change (Noema#907 follow-up comment, operator decision).
