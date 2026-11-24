"""Synthetic Controller group supervisor (D-006, D-007). Not a PSR-1 cohort."""

import threading
from typing import Callable, Mapping

from .ports import CommandClient, DecisionAdapter
from .profiles import select
from .receipts import SOURCE_SHA
from .runner import run

MAX_GROUP_SIZE = 6
_COUNTED = ("ATTEMPTED", "FAILED_SUBMISSION", "REFUSED", "STOPPED")


def _summary(status: str, size: object, members: list[dict[str, object]]) -> dict[str, object]:
    counts = {key: sum(1 for m in members if m["status"] == key) for key in _COUNTED}
    return {
        "record": "GROUP_SUMMARY",
        "group_status": status,
        "group_size": size if type(size) is int and 1 <= size <= MAX_GROUP_SIZE else "INVALID",
        "counts": counts,
        "source_sha": SOURCE_SHA,
        "claim_label": "SPECULATIVE",
        "evidence_scope": "SYNTHETIC_GROUP_ONLY",
    }


def run_group(*, profile: str, fixture: Mapping[str, object] | None, size: object,
              client_factory: Callable[[str], CommandClient],
              adapter_factory: Callable[[str], DecisionAdapter],
              stop: threading.Event | None = None,
              before_member: Callable[[], None] | None = None,
              ) -> tuple[list[dict[str, object]], dict[str, object]]:
    """Run members sequentially, each with its own identity, client and adapter.

    A member failure never retries or halts others. A set ``stop`` event is the
    group stop: every member not yet started is recorded as STOPPED.
    """
    stop = stop or threading.Event()
    if select(profile) is not None or type(size) is not int or not 1 <= size <= MAX_GROUP_SIZE:
        return [], _summary("REFUSED", size, [])
    members: list[dict[str, object]] = []
    for index in range(1, size + 1):
        member_id = f"member-{index:02d}"
        if before_member is not None and not stop.is_set():
            before_member()
        if stop.is_set():
            members.append({"member_id": member_id, "status": "STOPPED"})
            continue
        client = client_factory(member_id)
        adapter = adapter_factory(member_id)
        outcome = run(profile=profile, fixture=fixture, client=client, adapter=adapter)
        members.append({"member_id": member_id, **outcome})
    statuses = {m["status"] for m in members}
    if "STOPPED" in statuses:
        status = "STOPPED"
    elif statuses == {"ATTEMPTED"}:
        status = "ATTEMPTED"
    elif "ATTEMPTED" in statuses:
        status = "PARTIAL"
    else:
        status = "FAILED"
    return members, _summary(status, size, members)
