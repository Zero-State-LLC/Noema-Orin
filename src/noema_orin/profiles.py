"""Explicit synthetic targets; no network configuration or fallback."""


def select(profile: object) -> str | None:
    """Return a safe refusal code, or None for the only runnable profile."""
    if type(profile) is not str:
        return "INVALID_PROFILE"
    if profile == "hosted":
        return None
    if profile == "offline-spark":
        return "BLOCKED_SPEC_DEFECT"
    return "INVALID_PROFILE"
