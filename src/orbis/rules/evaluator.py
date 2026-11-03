"""Evaluator contract for later milestones; M4.1 ships no D-01–D-05 implementation."""
from typing import Protocol, Any


class RuleEvaluator(Protocol):
    def evaluate(self, context: dict[str, Any], parameters: dict[str, Any]) -> list[dict[str, Any]]: ...
