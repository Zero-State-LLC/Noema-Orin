"""Civic role roster for persistent Orin Agent Players (docs/SYSTEM-ROLES.md, D-009).

Pure data. A role narrows what a member's Controller may propose; it never grants
world authority. Office powers come only from seats held in-world.
"""

BASE = ("LOOK", "MOVE", "INSPECT", "WAIT", "OBSERVE", "ENTER_WORLD")

ROLES: dict[str, dict[str, object]] = {
    "founder": {"allow": BASE + ("ORG_CREATE", "ORG_INVITE", "MESSAGE"),
                "brief": "Found one civic organization and invite the other Orin members. Do not trade."},
    "quartermaster": {"allow": BASE + ("HARVEST", "COMMIT.HARVEST"),
                      "brief": "Keep stores stocked. HARVEST when stock and storage allow, else WAIT. Never trade."},
    "custodian": {"allow": BASE + ("REPAIR", "COMMIT.REPAIR"),
                  "brief": "Patrol infrastructure. REPAIR damaged relays when affordable; report condition."},
    "archivist": {"allow": BASE + ("RECONSTRUCT", "RECONSTRUCT_PUBLISH", "ATTEST"),
                  "brief": "INSPECT artifacts and keep an honest record. Never invent history."},
    "speaker": {"allow": BASE + ("MESSAGE",),
                "brief": "Relay observed conditions to others with MESSAGE. Ground every claim in what you saw."},
    "spare": {"allow": BASE, "brief": "Observe and move. Take no economic action."},
}

DENY_ALWAYS = ("TRADE", "TRADE_PROPOSE", "ACCESS_GRANT", "CONTEST")


def role_for(name: object) -> dict[str, object]:
    if type(name) is not str or name not in ROLES:
        raise ValueError("unknown role")
    return ROLES[name]
