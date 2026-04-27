"""
Node: save_response

Persists the agent's final response and marks the original event resolved.
"""

import uuid

from agent.state import ACLWorkflowState
from repositories.conversation_event import ConversationEventRepository


def save_response(state: ACLWorkflowState, *, db) -> dict:
    repo = ConversationEventRepository(db)
    ctx = state["patient_context"]

    repo.create(
        event_id=f"evt_{uuid.uuid4().hex[:12]}",
        patient_id=state["patient_id"],
        role="agent",
        message_text=state["final_response"],
        phase=ctx["phase"],
        postop_day=ctx.get("postop_day"),
        status="resolved",
    )

    original_event = repo.get(state["conversation_event_id"])
    if original_event:
        repo.update(original_event.event_id, status="resolved")

    db.commit()

    return {}
