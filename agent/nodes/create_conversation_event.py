"""
Node: create_conversation_event

Persists the inbound patient message as a ConversationEvent row.
"""

import uuid

from agent.state import ACLWorkflowState
from repositories.conversation_event import ConversationEventRepository


def create_conversation_event(state: ACLWorkflowState, *, db) -> dict:
    repo = ConversationEventRepository(db)
    ctx = state["patient_context"]

    event = repo.create(
        event_id=f"evt_{uuid.uuid4().hex[:12]}",
        patient_id=state["patient_id"],
        role="patient",
        message_text=state["user_message"],
        phase=ctx["phase"],
        postop_day=ctx.get("postop_day"),
        status="pending",
    )
    db.commit()

    return {"conversation_event_id": event.event_id}
