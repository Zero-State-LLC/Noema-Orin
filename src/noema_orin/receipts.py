"""Allowlisted local telemetry, never canonical world evidence."""

SOURCE_SHA = "619d0674518761aa08462d3f5d5966a917259aa1"
_RESULTS = frozenset({"INVALID_PROFILE", "BLOCKED_SPEC_DEFECT", "INVALID_FIXTURE", "INVALID_PROPOSAL", "INVALID_INVOCATION", "DRY_RUN_REQUIRED", "TRANSPORT_FAILURE", "FAKE_HANDOFF"})
_STATUSES = frozenset({"REFUSED", "FAILED_SUBMISSION", "ATTEMPTED"})


def receipt(status: str, result: str, *, hosted: bool = False, handoff: bool = False) -> dict[str, object]:
    """Create a receipt only from trusted outcome codes, not input or client data."""
    if status not in _STATUSES or result not in _RESULTS:
        raise ValueError("unrecognized synthetic outcome")
    record: dict[str, object] = {
        "status": status,
        "result": result,
        "source_sha": SOURCE_SHA,
        "claim_label": "SPECULATIVE",
        "client_version": "UNVERIFIED",
        "device_metrics": "NOT_COMPUTABLE",
    }
    if hosted:
        record["profile"] = "hosted"
    if handoff:
        record["transport"] = "fake"
        record["action"] = "LOOK"
    return record
