"""
Conditional edge / terminal node: escalate_if_needed

Logs the escalation if needed. In a future phase this will also
send an SMS/page to the on-call clinician.
"""

import structlog

from agent.state import ACLWorkflowState

logger = structlog.get_logger()


def escalate_if_needed(state: ACLWorkflowState, *, db) -> dict:
    if not state.get("escalation_needed"):
        return {}

    rule_result = state.get("rule_result", {})
    logger.warning(
        "escalation_triggered",
        patient_id=state["patient_id"],
        risk_level=rule_result.get("risk_level"),
        triggered_rules=rule_result.get("triggered_rules"),
    )

    return {}
