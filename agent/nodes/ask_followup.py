"""
Node: ask_followup

Generates targeted clarifying questions when extraction is ambiguous.
"""

import uuid
import structlog
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI

from agent.state import ACLWorkflowState
from repositories.conversation_event import ConversationEventRepository
from api.config import settings

logger = structlog.get_logger()

FOLLOWUP_SYSTEM_PROMPT = """\
You are a compassionate clinical assistant helping a patient after ACL surgery.

The patient's message was unclear, and we need ONE specific piece of information \
to provide proper guidance.

Your task: Ask a SINGLE, SPECIFIC clarifying question based on what's missing.

Guidelines:
1. Be warm, calm, and reassuring
2. Ask about ONE thing only (the most important missing field)
3. Keep it to 1-2 sentences
4. Make it conversational, not clinical
5. Never say "can you tell me more" - be specific

Priority order (ask about the MOST important one first):
1. Location (knee vs calf is critical for DVT assessment)
2. Severity (pain scale 1-10 for triage)
3. Fever (yes/no matters for infection)
4. Calf symptoms (swelling, pain - critical for DVT)
5. Other symptoms

Examples:
- Missing location: "To help you best, can you tell me if the pain is in your knee or in your calf?"
- Missing severity: "On a scale of 1-10, how would you rate your pain right now?"
- Missing fever: "Do you have a fever? Have you taken your temperature today?"
- Missing calf location: "Just to be sure - is the swelling in your calf or somewhere else?"
- Multiple missing: Pick the most clinically important one (location > severity > fever)
"""

FOLLOWUP_USER_PROMPT = """\
Patient phase: {phase}
Patient's original message: "{patient_message}"

Missing fields that need clarification: {missing_fields}

Recent conversation history for context:
{recent_history}

Generate a warm, specific clarifying question asking about the MOST IMPORTANT missing field.
"""


def _get_most_important_field(missing_fields: list[str]) -> str:

    priority_map = {
        "location": 1,
        "calf_location_confirmed": 2,
        "pain_location": 2,
        "severity_score": 3,
        "pain_severity": 3,
        "fever": 4,
        "calf_pain": 5,
        "calf_swelling": 5,
        "drainage": 6,
        "swelling": 7,
        "warmth": 7,
        "redness": 7,
    }
    
    sorted_fields = sorted(
        missing_fields,
        key=lambda f: priority_map.get(f.lower(), 999)
    )
    
    return sorted_fields[0] if sorted_fields else "details"


def _build_followup_chain():
    llm = ChatOpenAI(
        model="gpt-5.4-mini",
        temperature=0.3,
        api_key=settings.openai_api_key,
    )
    
    prompt = ChatPromptTemplate.from_messages([
        ("system", FOLLOWUP_SYSTEM_PROMPT),
        ("user", FOLLOWUP_USER_PROMPT),
    ])
    
    return prompt | llm | StrOutputParser()


def _run_followup_chain(
    patient_message: str,
    phase: str,
    missing_fields: list[str],
    recent_history: list[dict],
) -> str:
    try:
        chain = _build_followup_chain()
        
        # Format recent history for context
        history_text = "\n".join([
            f"- {h['role']}: {h['message_text']}"
            for h in recent_history[-3:]  # Last 3 messages
        ]) if recent_history else "No prior conversation"
        
        # Identify most important missing field
        most_important = _get_most_important_field(missing_fields)
        fields_str = ", ".join(missing_fields)
        
        result = chain.invoke({
            "patient_message": patient_message,
            "phase": phase,
            "missing_fields": f"{fields_str} (prioritize: {most_important})",
            "recent_history": history_text,
        })
        
        logger.info(
            "followup_chain_success",
            missing_fields=missing_fields,
            prioritized_field=most_important,
        )
        
        return result.strip()
    
    except Exception as e:
        logger.error("followup_chain_failed", error=str(e))
        
        # Fallback based on most important missing field
        most_important = _get_most_important_field(missing_fields)
        
        if "location" in most_important.lower() or "calf" in most_important.lower():
            return "To help you best, can you tell me if the discomfort is in your knee or in your calf?"
        elif "severity" in most_important.lower() or "pain" in most_important.lower():
            return "On a scale of 1-10, how would you rate your pain right now?"
        elif "fever" in most_important.lower():
            return "Do you have a fever? Have you taken your temperature today?"
        else:
            return "Can you tell me a bit more about what you're experiencing?"


def ask_followup(state: ACLWorkflowState, *, db) -> dict:
    extraction_result = state.get("extraction_result", {})
    patient_context = state.get("patient_context", {})
    user_message = state.get("user_message", "")
    recent_history = state.get("recent_history", [])
    
    missing_fields = extraction_result.get("missing_fields", [])
    phase = patient_context.get("phase", "post_op")
    
    # Generate targeted follow-up question
    followup_text = _run_followup_chain(
        patient_message=user_message,
        phase=phase,
        missing_fields=missing_fields,
        recent_history=recent_history,
    )
    
    # Save to database
    repo = ConversationEventRepository(db)
    
    # Save the followup question as an agent message
    repo.create(
        event_id=f"evt_{uuid.uuid4().hex[:12]}",
        patient_id=state["patient_id"],
        role="agent",
        message_text=followup_text,
        phase=phase,
        postop_day=patient_context.get("postop_day"),
        status="sent",
    )
    
    # Mark the original patient message as pending followup
    original_event = repo.get(state["conversation_event_id"])
    if original_event:
        repo.update(original_event.event_id, status="pending_followup")
    
    db.commit()
    
    logger.info(
        "followup_question_saved",
        patient_id=state["patient_id"],
        missing_fields=missing_fields,
    )
    
    return {"final_response": followup_text}
