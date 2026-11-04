"""SQL persistence primitives. The caller owns transaction boundaries."""
import json
from datetime import datetime, timezone
from psycopg.types.json import Jsonb
from .evidence import verify_envelope
from .normalization import digest
from orbis.network import NetworkContext, TrustState


class EvaluationRepository:
    def __init__(self, connection): self.db = connection

    def _verify_request(self, *, context, network_id, rule_version, from_block, to_block, parameters,
                        context_digest, evaluator_build, envelope):
        if (not isinstance(context, NetworkContext) or context.state is not TrustState.TRUSTED
                or context.network_id != network_id):
            raise ValueError("rules request requires its exactly resolved NetworkContext")
        row = self.db.execute("SELECT chain_id,fingerprint_scheme,network_fingerprint,genesis_hash FROM networks WHERE network_id=%s",(network_id,)).fetchone()
        if row is None: raise LookupError("network not found")
        if (row["chain_id"],row["fingerprint_scheme"],row["network_fingerprint"],row["genesis_hash"]) != (
                context.chain_id,context.fingerprint_scheme,context.network_fingerprint,context.genesis_hash):
            raise ValueError("rules NetworkContext does not match registered identity")
        if envelope.get("network_chain_id") != row["chain_id"]: raise ValueError("evidence network does not match evaluation network")
        if envelope.get("bounds") != {"from":from_block,"to":to_block}: raise ValueError("evidence bounds do not match evaluation bounds")
        if envelope.get("parameters") != parameters: raise ValueError("evidence parameters do not match evaluation parameters")
        if envelope.get("context_digest") != context_digest: raise ValueError("evidence context does not match evaluation context")
        if envelope.get("evaluator",{}).get("build_identity") != evaluator_build: raise ValueError("evidence build does not match evaluation build")
        rule=envelope.get("rule",{})
        if (rule.get("rule_id"),rule.get("semantic_version"),rule.get("definition_digest")) != (rule_version["rule_id"],rule_version["semantic_version"],rule_version["definition_digest"]):
            raise ValueError("evidence rule version does not match evaluation rule version")
        if any(item.get("network_chain_id") != row["chain_id"] or not from_block <= item.get("block_number",-1) <= to_block for item in envelope.get("items",[])):
            raise ValueError("evidence item is outside evaluation network or block bounds")
        identities={(item["block_number"],item["block_hash"]) for item in envelope.get("items",[])}
        if identities:
            source=self.db.execute("""SELECT number,hash FROM blocks WHERE network_id=%s AND hash=ANY(%s)
                AND canonical ORDER BY number FOR KEY SHARE""",(network_id,[h for _,h in identities])).fetchall()
            canonical={(r["number"],r["hash"]) for r in source}
            if canonical != identities: raise ValueError("evaluation evidence is not backed by canonical source blocks")

    def create(self, *, context, network_id, rule_version, subject_kind, subject_key, from_block, to_block,
               parameters, context_digest, evaluator_build, evaluation_key, coverage, envelope,
               outcome, findings=(), diagnostics=None, supersedes_evaluation_id=None):
        verify_envelope(envelope)
        if outcome not in {"matched","not_matched","insufficient_coverage"}: raise ValueError("invalid outcome")
        if outcome == "not_matched" and coverage.get("insufficient_dimensions"): outcome="insufficient_coverage"
        if outcome == "matched" and not findings: raise ValueError("matched evaluations require at least one finding")
        if outcome != "matched" and findings: raise ValueError("only matched evaluations may contain findings")
        parameter_digest = digest(parameters)
        now = datetime.now(timezone.utc)
        with self.db.transaction():
            self._verify_request(context=context,network_id=network_id,rule_version=rule_version,from_block=from_block,to_block=to_block,
                parameters=parameters,context_digest=context_digest,evaluator_build=evaluator_build,envelope=envelope)
            row = self.db.execute("""INSERT INTO evaluations(network_id,rule_version_id,rule_id,subject_kind,subject_key,
                from_block,to_block,normalized_parameters,parameter_digest,context_digest,evaluator_build,evaluation_key,
                execution_status,analytical_outcome,coverage,evidence_envelope,evidence_digest,digest_algorithm,
                evidence_schema_version,diagnostics,started_at,completed_at,supersedes_evaluation_id)
                VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'completed',%s,%s,%s,%s,'sha256',1,%s,%s,%s,%s)
                ON CONFLICT(network_id,evaluation_key) DO NOTHING RETURNING *""",
                (network_id,rule_version["rule_version_id"],rule_version["rule_id"],subject_kind,subject_key,
                 from_block,to_block,Jsonb(parameters),parameter_digest,context_digest,evaluator_build,evaluation_key,
                 outcome,Jsonb(coverage),Jsonb(envelope),envelope["evidence_digest"],Jsonb(diagnostics or {}),now,now,supersedes_evaluation_id)).fetchone()
            if row is None:
                row = self.db.execute("SELECT * FROM evaluations WHERE network_id=%s AND evaluation_key=%s FOR UPDATE",(network_id,evaluation_key)).fetchone()
                if row["evidence_digest"] != envelope["evidence_digest"]: raise ValueError("evaluation identity collision")
                return row
            items = envelope.get("items", [])
            for ordinal,item in enumerate(items):
                self.db.execute("""INSERT INTO evaluation_evidence VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                    (network_id,row["evaluation_id"],ordinal,item["evidence_digest"],item["block_number"],item["block_hash"],
                     item.get("transaction_hash"),item.get("log_index"),item["source_kind"],Jsonb(item["normalized_input"]),"sha256",item["schema_version"]))
            for attempt_status in ("completed",):
                self.db.execute("INSERT INTO evaluation_attempts VALUES(%s,%s,1,%s,%s,%s,%s)",
                    (network_id,row["evaluation_id"],attempt_status,Jsonb(diagnostics or {}),now,now))
            for finding in findings:
                key = finding.get("finding_key") or digest(finding["result"])
                found = self.db.execute("""INSERT INTO findings(network_id,evaluation_id,rule_version_id,finding_key,result)
                    VALUES(%s,%s,%s,%s,%s) ON CONFLICT(network_id,evaluation_id,finding_key) DO NOTHING RETURNING finding_id""",
                    (network_id,row["evaluation_id"],rule_version["rule_version_id"],key,Jsonb(finding["result"]))).fetchone()
                if found:
                    selected = finding.get("evidence", items)
                    by_digest = {x["evidence_digest"]:x for x in items}
                    for ordinal,item in enumerate(selected):
                        canonical = by_digest.get(item.get("evidence_digest"))
                        if canonical is None: raise ValueError("finding evidence must belong to evaluation envelope")
                        self.db.execute("""INSERT INTO finding_evidence VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                            (network_id,found["finding_id"],ordinal,canonical["evidence_digest"],canonical["source_kind"],canonical["block_number"],canonical["block_hash"],canonical.get("transaction_hash"),canonical.get("log_index"),Jsonb(canonical["normalized_input"]),"sha256",canonical["schema_version"]))
            return row

    def record_failure(self, *, context, network_id, rule_version, subject_kind, subject_key, from_block, to_block,
                       parameters, context_digest, evaluator_build, evaluation_key, coverage, envelope,
                       diagnostics, attempt_no=1):
        verify_envelope(envelope)
        now=datetime.now(timezone.utc)
        with self.db.transaction():
            self._verify_request(context=context,network_id=network_id,rule_version=rule_version,from_block=from_block,to_block=to_block,
                parameters=parameters,context_digest=context_digest,evaluator_build=evaluator_build,envelope=envelope)
            row=self.db.execute("""INSERT INTO evaluations(network_id,rule_version_id,rule_id,subject_kind,subject_key,
                from_block,to_block,normalized_parameters,parameter_digest,context_digest,evaluator_build,evaluation_key,
                execution_status,analytical_outcome,coverage,evidence_envelope,evidence_digest,digest_algorithm,
                evidence_schema_version,diagnostics,started_at)
                VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'failed',NULL,%s,%s,%s,'sha256',1,%s,%s)
                ON CONFLICT(network_id,evaluation_key) DO NOTHING RETURNING *""",
                (network_id,rule_version["rule_version_id"],rule_version["rule_id"],subject_kind,subject_key,from_block,to_block,
                 Jsonb(parameters),digest(parameters),context_digest,evaluator_build,evaluation_key,Jsonb(coverage),Jsonb(envelope),
                 envelope["evidence_digest"],Jsonb(diagnostics),now)).fetchone()
            if row is None: return self.db.execute("SELECT * FROM evaluations WHERE network_id=%s AND evaluation_key=%s",(network_id,evaluation_key)).fetchone()
            for i,item in enumerate(envelope.get("items",[])):
                self.db.execute("INSERT INTO evaluation_evidence VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'sha256',%s)",
                    (network_id,row["evaluation_id"],i,item["evidence_digest"],item["block_number"],item["block_hash"],item.get("transaction_hash"),item.get("log_index"),item["source_kind"],Jsonb(item["normalized_input"]),item["schema_version"]))
            self.db.execute("INSERT INTO evaluation_attempts VALUES(%s,%s,%s,'failed',%s,%s,%s)",(network_id,row["evaluation_id"],attempt_no,Jsonb(diagnostics),now,now))
            return row

    def get(self, context, evaluation_id):
        if not isinstance(context, NetworkContext) or context.state is not TrustState.TRUSTED or not context.network_id:
            raise ValueError("rules retrieval requires an exactly resolved NetworkContext")
        network_id = context.network_id
        registered = self.db.execute("""SELECT chain_id,fingerprint_scheme,network_fingerprint,genesis_hash
            FROM networks WHERE network_id=%s""", (network_id,)).fetchone()
        if registered is None or (registered["chain_id"],registered["fingerprint_scheme"],
                registered["network_fingerprint"],registered["genesis_hash"]) != (
                context.chain_id,context.fingerprint_scheme,context.network_fingerprint,context.genesis_hash):
            raise ValueError("rules retrieval context does not match registered identity")
        row=self.db.execute("SELECT * FROM evaluations WHERE network_id=%s AND evaluation_id=%s",(network_id,evaluation_id)).fetchone()
        if row is None: raise LookupError("evaluation not found")
        verify_envelope(row["evidence_envelope"])
        if row["evidence_digest"] != row["evidence_envelope"]["evidence_digest"]: raise ValueError("stored evidence digest mismatch")
        row["findings"]=self.db.execute("SELECT * FROM findings WHERE network_id=%s AND evaluation_id=%s ORDER BY finding_id",(network_id,evaluation_id)).fetchall()
        return row
