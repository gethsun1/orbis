"""PostgreSQL rule-version registry."""
from psycopg.types.json import Jsonb
from .normalization import digest


class RuleRegistry:
    def __init__(self, connection): self.db = connection

    @staticmethod
    def definition(rule_id, semantic_version, input_schema, parameter_schema, decoder_requirements, coverage_requirements):
        return {"rule_id":rule_id,"semantic_version":semantic_version,"input_schema":input_schema,
                "parameter_schema":parameter_schema,"decoder_requirements":decoder_requirements,
                "coverage_requirements":coverage_requirements}

    def register(self, *, rule_id, semantic_version, input_schema, parameter_schema,
                 decoder_requirements=None, coverage_requirements=None, created_by=None):
        decoder_requirements = decoder_requirements or []
        coverage_requirements = coverage_requirements or {}
        definition = self.definition(rule_id,semantic_version,input_schema,parameter_schema,decoder_requirements,coverage_requirements)
        definition_digest = digest(definition)
        row = self.db.execute("""INSERT INTO rule_versions(rule_id,semantic_version,definition_digest,input_schema,
            parameter_schema,decoder_requirements,coverage_requirements,lifecycle_state,created_by)
            VALUES(%s,%s,%s,%s,%s,%s,%s,'staged',%s)
            ON CONFLICT(rule_id,semantic_version) DO NOTHING RETURNING *""",
            (rule_id,semantic_version,definition_digest,Jsonb(input_schema),Jsonb(parameter_schema),Jsonb(decoder_requirements),Jsonb(coverage_requirements),created_by)).fetchone()
        row = row or self.get(rule_id, semantic_version)
        if row["definition_digest"] != definition_digest: raise ValueError("rule version already registered with a different definition")
        return row

    def get(self, rule_id, semantic_version):
        row = self.db.execute("SELECT * FROM rule_versions WHERE rule_id=%s AND semantic_version=%s",(rule_id,semantic_version)).fetchone()
        if not row: raise LookupError("rule version not found")
        return row

    def activate(self, rule_id, semantic_version, reason=None):
        row = self.get(rule_id,semantic_version)
        if row["lifecycle_state"] != "staged": raise ValueError("only staged versions can be activated")
        return self.db.execute("UPDATE rule_versions SET lifecycle_state='active',activated_at=now(),lifecycle_reason=%s WHERE rule_version_id=%s RETURNING *",(reason,row["rule_version_id"])).fetchone()

    def retire(self, rule_id, semantic_version, reason=None):
        row = self.get(rule_id,semantic_version)
        if row["lifecycle_state"] != "active": raise ValueError("only active versions can be retired")
        return self.db.execute("UPDATE rule_versions SET lifecycle_state='retired',retired_at=now(),lifecycle_reason=%s WHERE rule_version_id=%s RETURNING *",(reason,row["rule_version_id"])).fetchone()
