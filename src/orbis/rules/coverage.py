from __future__ import annotations

STATES = {"complete", "partial", "unknown", "not_applicable"}


def assess_coverage(dimensions: dict, required: list[str], *, not_applicable_allowed: bool = False) -> dict:
    normalized = {}
    for name, value in dimensions.items():
        state = value.get("state") if isinstance(value, dict) else value
        if state not in STATES: raise ValueError(f"invalid coverage state for {name}")
        normalized[name] = value if isinstance(value, dict) else {"state":state}
    missing = sorted(x for x in required if normalized.get(x, {}).get("state", "unknown") != "complete" and
                     not (not_applicable_allowed and normalized.get(x, {}).get("state") == "not_applicable"))
    state = "complete" if not missing else ("unknown" if any(normalized.get(x, {}).get("state", "unknown") == "unknown" for x in missing) else "partial")
    return {"schema_version":1,"state":state,"dimensions":normalized,"required_dimensions":list(required),"insufficient_dimensions":missing}


def gate_outcome(outcome: str, coverage: dict) -> str:
    if outcome not in {"matched","not_matched","insufficient_coverage"}: raise ValueError("invalid analytical outcome")
    if outcome == "not_matched" and coverage.get("insufficient_dimensions"): return "insufficient_coverage"
    return outcome
