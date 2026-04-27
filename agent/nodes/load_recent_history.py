"""
Node: load_recent_history

Fetches the last 5 conversation messages for the patient (chronological order).
"""

from agent.state import ACLWorkflowState
from repositories.conversation_event import ConversationEventRepository


def load_recent_history(state: ACLWorkflowState, *, db) -> dict:
    repo = ConversationEventRepository(db)
    events = repo.get_recent_by_patient(state["patient_id"], limit=5)

    history = [
        {"role": e.role, "message_text": e.message_text}
        for e in reversed(events)
    ]

    return {"recent_history": history}
