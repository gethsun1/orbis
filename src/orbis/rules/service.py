"""Persistence orchestration helpers. Evaluator implementations are deliberately absent."""
from .coverage import assess_coverage, gate_outcome
from .identity import evaluation_identity
from .normalization import normalize_parameters, normalize_subject
from .registry import RuleRegistry
from .repository import EvaluationRepository
from orbis.network import NetworkContext, TrustState


class EvaluationService:
    def __init__(self, connection):
        self.db = connection
        self.registry = RuleRegistry(connection)
        self.repository = EvaluationRepository(connection)

    def identity(self, *, context: NetworkContext, subject_kind, subject_key, rule_version, from_block, to_block, parameters, context_digest, evaluator_build):
        if context.state is not TrustState.TRUSTED or context.network_id is None:
            raise ValueError("rules evaluation requires an exactly resolved NetworkContext")
        normalized = normalize_parameters(parameters, rule_version["parameter_schema"])
        subject_key = normalize_subject(subject_kind, subject_key)
        key = evaluation_identity(chain_id=context.chain_id, network_fingerprint=context.network_fingerprint,
            subject_kind=subject_kind, subject_key=subject_key,
            rule_id=rule_version["rule_id"], semantic_version=rule_version["semantic_version"],
            definition_digest=rule_version["definition_digest"], from_block=from_block, to_block=to_block,
            parameters=normalized, context_digest=context_digest, evaluator_build=evaluator_build)
        return normalized, subject_key, key

    def persist_result(self, *, outcome, coverage, **request):
        context = request.pop("context", None)
        if not isinstance(context, NetworkContext) or context.state is not TrustState.TRUSTED:
            raise ValueError("rules persistence requires an exactly resolved NetworkContext")
        if request.get("network_id") != context.network_id:
            raise ValueError("rules network_id does not match resolved NetworkContext")
        request["context"] = context
        outcome = gate_outcome(outcome, coverage)
        return self.repository.create(outcome=outcome, coverage=coverage, **request)
