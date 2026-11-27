# Triage Labels

The skills speak in terms of five canonical triage roles. This file maps those roles to the actual label strings used in this repo's issue tracker.

<!-- agent-machine:triage:start · generated: edit .agents/procedures.json, then run `python3 .agents/docs.py render --write` -->
| Label in mattpocock/skills | Label in our tracker | Meaning |
| -------------------------- | -------------------- | ------- |
| `needs-triage` | `needs-triage` | Maintainer needs to evaluate this issue |
| `needs-info` | `needs-info` | Waiting on reporter for more information |
| `ready-for-agent` | `ready-for-agent` | Fully specified, ready for an AFK agent |
| `ready-for-human` | `ready-for-human` | Requires human implementation |
| `wontfix` | `wontfix` | Will not be actioned |

Each open issue carries exactly one triage label. It moves like this:

- `needs-triage` → `needs-info` when the reporter must add information · `ready-for-agent` when it is fully specified for an AFK agent · `ready-for-human` when it needs human implementation · `wontfix` when it will not be actioned
- `needs-info` → `needs-triage` when the reporter replies
- `ready-for-agent`: the issue closes when the work is done.
- `ready-for-human`: the issue closes when the work is done.
- `wontfix`: the issue closes.

Label strings live in `.agents/procedures.json` (`triage`); edit them there. `python3 .agents/docs.py triage-audit` lists open issues that break the rule.
<!-- agent-machine:triage:end -->

When a skill mentions a role (e.g. "apply the AFK-ready triage label"), use the corresponding label string from this table.
