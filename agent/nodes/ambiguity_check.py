"""
Conditional edge: ambiguity_check

Routes the workflow based on whether the extraction was clear or unclear.
"""

from agent.state import ACLWorkflowState


def ambiguity_check(state: ACLWorkflowState) -> str:
    patient_context = state.get("patient_context") or {}
    if patient_context.get("phase") == "pre_op":
        return "retrieve_knowledge"

    if state.get("ambiguity_status") == "unclear":
        return "ask_followup"
    return "retrieve_knowledge"
