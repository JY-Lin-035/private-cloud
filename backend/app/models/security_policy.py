from sqlalchemy import Column, Integer, String, Text

from .base import BaseModel


class SecurityPolicyVersion(BaseModel):
    """Immutable, append-only version of the risk-threshold overrides.

    The row id IS the version number. Writing settings inserts a new row whose
    payload is the FULL set of admin overrides (not a delta), which makes
    "restore default" (drop keys) and "rollback" (copy an older payload) both
    plain inserts. `diff` records what that version changed, for audit.

    Counters/blocks are NOT stored here: changing a threshold never resets a
    running window nor lifts an existing rule.
    """

    __tablename__ = "security_policy_versions"

    payload = Column(Text, nullable=False)          # JSON {policy_id: int}
    diff = Column(Text, nullable=True)              # JSON {policy_id: {before, after}}
    reason = Column(String(255), nullable=True)
    actor = Column(String(128), nullable=True)      # admin username
    actor_id = Column(Integer, nullable=True)
    parent_version = Column(Integer, nullable=True)
    action = Column(String(16), nullable=False, default="update")  # update|reset|rollback
