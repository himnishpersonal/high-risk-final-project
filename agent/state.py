"""
LangGraph workflow state definition.
"""

from typing import Optional, TypedDict

class ACLWorkflowState(TypedDict, total=False):
    patient_id: str
    user_message: str
    patient_context: dict
    recent_history: list
    conversation_event_id: str
    extraction_result: Optional[dict]
    ambiguity_status: str
    retrieved_knowledge: list
    rule_result: Optional[dict]
    final_response: str
    escalation_needed: bool
