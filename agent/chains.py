"""
LangChain LCEL chains for the ACL monitoring agent.

Chains:
  - build_extraction_chain / run_extraction  — structured clinical extraction
  - run_routine_response   — reassuring post-op reply (routine risk)
  - run_escalation_response — patient msg + clinician summary (medium/high/emergency)
  - run_preop_response      — informational pre-op answer
"""

import structlog
from langchain_core.output_parsers import PydanticOutputParser, StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI

from agent.schemas import ALLOWED_SYMPTOMS, ClinicalExtractionResult
from api.config import settings

logger = structlog.get_logger()


def _get_llm(temperature: float = 0.3) -> ChatOpenAI:
    return ChatOpenAI(
        model="gpt-5.4-mini",
        temperature=temperature,
        api_key=settings.openai_api_key,
    )

_SYMPTOMS_LIST = ", ".join(sorted(ALLOWED_SYMPTOMS))

_PRIOR_KEYWORDS = ["again", "still", "same", "worse", "back", "keeps"]

EXTRACTION_SYSTEM_PROMPT = """\
You are a clinical data extraction engine for an ACL post-operative monitoring system.

Return ONLY valid JSON. No prose, no markdown, no code fences. Use null for unknown fields.

Your output must conform to the following schema:
{format_instructions}

Rules:

1. SYMPTOM VOCABULARY
   Map the patient's natural language to ONLY these controlled symptom values:
   {symptoms_list}
   If the patient describes something that does not map to one of these, do NOT include it.

2. AMBIGUITY
   ambiguity_status = "unclear" applies ONLY to post-op patients reporting
   physical symptoms where critical clinical details are missing.

   Set ambiguity_status to "unclear" ONLY if ALL of these are true:
   - The patient is post-op (phase = post_op)
   - The patient is reporting a physical symptom or complaint
   - The message is completely missing BOTH a body location AND a symptom type
     (e.g. "something is wrong" or "I don't feel right" with no other detail)

   Set ambiguity_status to "clear" in ALL of these cases:
   - Patient is pre-op (always clear — see Rule 4)
   - Patient is asking a question (any question, even vague)
   - Patient is expressing emotion, anxiety, or general concern
   - Patient mentions any specific body part OR any specific symptom
   - Patient is having a conversation rather than reporting acute symptoms

   Use missing_fields ONLY for post-op symptom reports where the missing
   field would materially change the triage decision:
   - "location" if leg symptom mentioned but knee vs calf is unclear
   - "severity_score" if pain severity is critical to distinguish routine vs urgent
   Do NOT add missing_fields for questions, emotions, or general concerns.

3. REFERENCES TO PRIOR MESSAGES
   Set references_prior to true if the message contains any of these words:
   {prior_keywords}
   Otherwise set references_prior to false.

4. PRE-OP PHASE RULES
   When patient phase is "pre_op":
   - intent MUST be "preop_question" or "activity_question"
   - symptoms list MUST be empty [] — EXCEPT for these two emergency symptoms
     which must ALWAYS be extracted regardless of phase:
       * "shortness_of_breath" — if the patient reports difficulty breathing,
         trouble breathing, can't breathe, or breathlessness
       * "chest_pain" — if the patient reports chest pain, chest tightness,
         chest pressure, or heart pain
   - ambiguity_status MUST be "clear" — pre-op messages are never unclear,
     even if the patient is emotional, anxious, or vague. They are asking
     a question or expressing a concern, not reporting clinical symptoms.
   - missing_fields MUST be [] for pre-op patients
   - Focus only on the topic of the patient's question or concern

5. POST-OP PHASE RULES
   When patient phase is "post_op":
   - intent is usually "postop_symptom_check" or "general_concern"
   - Extract all mentioned symptoms into the controlled vocabulary
   - Populate symptoms_details with location, severity_score (0-10), and trend

6. SEVERITY SCORE
   Only populate severity_score if the patient gives a numeric pain rating.
   Do NOT guess. Use null if not explicitly stated.

7. TREND
   Set trend to "worsening", "stable", "improving", or "unknown" based on the
   patient's words. Default to "unknown" if not mentioned."""

EXTRACTION_USER_PROMPT = """\
Patient phase: {phase}
Post-op day: {postop_day}

Recent conversation:
{recent_history}

Current patient message:
{user_message}"""


def build_extraction_chain():

    parser = PydanticOutputParser(pydantic_object=ClinicalExtractionResult)

    prompt = ChatPromptTemplate.from_messages(
        [
            ("system", EXTRACTION_SYSTEM_PROMPT),
            ("human", EXTRACTION_USER_PROMPT),
        ]
    )

    llm = _get_llm(temperature=0)

    chain = prompt | llm | parser

    return chain, parser


def run_extraction(
    user_message: str,
    phase: str,
    postop_day: int,
    recent_history: list[dict],
) -> ClinicalExtractionResult:
    
    chain, parser = build_extraction_chain()

    history_str = _format_history(recent_history)

    try:
        result = chain.invoke(
            {
                "format_instructions": parser.get_format_instructions(),
                "symptoms_list": _SYMPTOMS_LIST,
                "prior_keywords": ", ".join(_PRIOR_KEYWORDS),
                "phase": phase,
                "postop_day": postop_day,
                "recent_history": history_str,
                "user_message": user_message,
            }
        )
        logger.info(
            "extraction_chain_success",
            intent=result.intent,
            symptoms=result.symptoms,
            ambiguity=result.ambiguity_status,
        )
        return result

    except Exception as e:
        logger.error("extraction_chain_failed", error=str(e))
        return ClinicalExtractionResult(
            intent="general_concern",
            symptoms=[],
            ambiguity_status="unclear",
            missing_fields=["all — LLM extraction failed"],
            references_prior=False,
        )


def _format_history(recent_history: list[dict]) -> str:
    if not recent_history:
        return "(no prior messages)"

    lines = []
    for msg in recent_history:
        role = msg.get("role", "unknown")
        text = msg.get("message_text", "")
        lines.append(f"[{role}]: {text}")
    return "\n".join(lines)


_ROUTINE_SYSTEM = """\
You are a compassionate post-operative recovery assistant for ACL surgery patients.
Your job is to reassure the patient that their reported symptoms are within the
expected range for their specific recovery day.

Rules:
- Reference the exact post-op day ("At day {postop_day} after ACL surgery…").
- If knowledge chunks are provided, ground your answer in them. Otherwise use
  general ACL recovery knowledge.
- Never make clinical decisions. Never say "you're fine" or "nothing to worry about".
  Instead explain what is normal and encourage them.
- Maximum 3–4 sentences. Warm, conversational tone — not robotic.
- Do NOT repeat the patient's message back to them verbatim.
- Plain text only — no markdown, no bold, no bullet points."""

_ROUTINE_USER = """\
Patient: {patient_name} | Phase: {phase} | Post-op day: {postop_day} | Graft: {graft_type}
Symptoms extracted: {symptoms}
Symptom details: {symptoms_details}

Knowledge context:
{knowledge}

Recent conversation:
{recent_history}

Current patient message:
{user_message}"""


def _format_knowledge(retrieved_knowledge: list) -> str:

    if not retrieved_knowledge:
        return "(none)"
    
    chunks = []
    for chunk in retrieved_knowledge:
        if isinstance(chunk, dict):
            text = chunk.get("text", "")
            source = chunk.get("source_id", "unknown")
            chunks.append(f"[Source: {source}]\n{text}")
        else:
            chunks.append(str(chunk))
    
    return "\n\n".join(chunks)


def run_routine_response(
    *,
    patient_context: dict,
    extraction_result: dict,
    retrieved_knowledge: list,
    recent_history: list[dict],
    user_message: str,
) -> str:
    prompt = ChatPromptTemplate.from_messages([
        ("system", _ROUTINE_SYSTEM),
        ("human", _ROUTINE_USER),
    ])
    chain = prompt | _get_llm(temperature=0.4) | StrOutputParser()

    details = extraction_result.get("symptoms_details") or {}
    knowledge_str = _format_knowledge(retrieved_knowledge)

    try:
        result = chain.invoke({
            "patient_name": patient_context.get("name", ""),
            "phase": patient_context.get("phase", "post_op"),
            "postop_day": patient_context.get("postop_day", 0),
            "graft_type": patient_context.get("graft_type") or "unknown",
            "symptoms": ", ".join(extraction_result.get("symptoms", [])) or "none",
            "symptoms_details": str(details),
            "knowledge": knowledge_str,
            "recent_history": _format_history(recent_history),
            "user_message": user_message,
        })
        logger.info("routine_response_success")
        return result.strip()
    except Exception as e:
        logger.error("routine_response_failed", error=str(e))
        postop_day = patient_context.get("postop_day", 0)
        return (
            f"Thank you for the update. What you're describing is common "
            f"at day {postop_day} of ACL recovery. Keep following your protocol "
            f"and reach out if anything changes."
        )


_ESCALATION_PATIENT_SYSTEM = """\
You are a calm, compassionate post-operative assistant for ACL surgery patients.
A clinical rule has flagged this patient's message. Your job is to inform the
patient clearly and helpfully — they deserve to understand what is happening
and what to do next, not just be told "care team is aware."

Follow these rules based on risk_level:

EMERGENCY:
- Tell them to call 911 immediately. One sentence. Nothing else.

HIGH:
- In 1 sentence, briefly explain why this symptom needs same-day attention
  (e.g. calf pain after surgery warrants prompt evaluation for circulation).
- Tell them to contact their care team TODAY — not "if it gets worse."
- Give 1–2 specific red flags that mean call 911 instead
  (e.g. shortness of breath, chest pain, rapid spreading swelling).
- 3 sentences max. Direct but calm.

MEDIUM:
- In 1 sentence, briefly explain what the symptom pattern may indicate
  (e.g. isolated fever can sometimes reflect your body fighting mild inflammation).
- Give 2–3 specific things to watch for in the next 24 hours.
- Tell them exactly when to contact their care team (if fever reaches X,
  if new symptoms appear, etc.).
- 3–4 sentences. Warm and informative — they should feel guided, not alarmed.

All risk levels:
- If knowledge context is provided, use it to ground your explanation.
- Do NOT repeat the patient's message back verbatim.
- Plain text only — no markdown, no bold, no bullet points."""

_ESCALATION_PATIENT_USER = """\
Patient: {patient_name} | Post-op day: {postop_day} | Risk: {risk_level}
Triggered rules: {triggered_rules}

Knowledge context:
{knowledge}

Recent conversation:
{recent_history}

Current patient message:
{user_message}"""

_CLINICIAN_SYSTEM = """\
You are a clinical summary writer for an ACL post-operative monitoring system.
Write a concise, structured summary for a clinician reviewing an escalation.

Include: post-op day, symptoms reported, rules triggered, recommended action.
Use plain clinical English. 2–4 sentences. No patient-facing language."""

_CLINICIAN_USER = """\
Patient: {patient_name} | Post-op day: {postop_day} | Graft: {graft_type}
Symptoms: {symptoms}
Symptom details: {symptoms_details}
Risk level: {risk_level}
Triggered rules: {triggered_rules}
Recommended action: {recommended_action}

Recent conversation:
{recent_history}

Current patient message:
{user_message}"""


def run_escalation_response(
    *,
    patient_context: dict,
    extraction_result: dict,
    rule_result: dict,
    retrieved_knowledge: list,
    recent_history: list[dict],
    user_message: str,
) -> tuple[str, str]:
    
    llm = _get_llm(temperature=0.3)
    risk_level = rule_result.get("risk_level", "medium")
    triggered_rules = ", ".join(rule_result.get("triggered_rules", []))
    details = extraction_result.get("symptoms_details") or {}
    knowledge_str = _format_knowledge(retrieved_knowledge)

    common_vars = {
        "patient_name": patient_context.get("name", ""),
        "postop_day": patient_context.get("postop_day", 0),
        "graft_type": patient_context.get("graft_type") or "unknown",
        "symptoms": ", ".join(extraction_result.get("symptoms", [])) or "none",
        "symptoms_details": str(details),
        "risk_level": risk_level,
        "triggered_rules": triggered_rules,
        "recommended_action": rule_result.get("recommended_action", ""),
        "knowledge": knowledge_str,
        "recent_history": _format_history(recent_history),
        "user_message": user_message,
    }

    patient_prompt = ChatPromptTemplate.from_messages([
        ("system", _ESCALATION_PATIENT_SYSTEM),
        ("human", _ESCALATION_PATIENT_USER),
    ])
    patient_chain = patient_prompt | llm | StrOutputParser()

    clinician_prompt = ChatPromptTemplate.from_messages([
        ("system", _CLINICIAN_SYSTEM),
        ("human", _CLINICIAN_USER),
    ])
    clinician_chain = clinician_prompt | llm | StrOutputParser()

    try:
        patient_msg = patient_chain.invoke(common_vars).strip()
    except Exception as e:
        logger.error("escalation_patient_msg_failed", error=str(e))
        if risk_level == "emergency":
            patient_msg = "Please call 911 immediately."
        elif risk_level == "high":
            patient_msg = (
                "Please contact your care team today — "
                "we have flagged this for review."
            )
        else:
            patient_msg = (
                "We are monitoring this closely. "
                "Please contact your care team if symptoms worsen."
            )

    try:
        clinician_summary = clinician_chain.invoke(common_vars).strip()
    except Exception as e:
        logger.error("escalation_clinician_summary_failed", error=str(e))
        clinician_summary = (
            f"Day {common_vars['postop_day']}: {common_vars['symptoms']}. "
            f"Rules: {triggered_rules}. Action: {common_vars['recommended_action']}."
        )

    logger.info(
        "escalation_response_success",
        risk_level=risk_level,
        triggered_rules=triggered_rules,
    )
    return patient_msg, clinician_summary


_PREOP_SYSTEM = """\
You are a friendly, educational assistant helping ACL surgery patients prepare
for their upcoming procedure.

Rules:
- Answer the patient's question with accurate, reassuring information.
- If knowledge chunks are provided, ground your answer in them. Otherwise use
  general ACL pre-op knowledge.
- No triage language whatsoever — no risk levels, no "contact your doctor".
- Maximum 3–4 sentences. Conversational, encouraging tone.
- Do NOT repeat the patient's question back to them verbatim.
- Plain text only — no markdown, no bold, no bullet points."""

_PREOP_USER = """\
Patient: {patient_name} | Surgery in: {days_until_surgery} days | Graft planned: {graft_type}

Knowledge context:
{knowledge}

Recent conversation:
{recent_history}

Current patient question:
{user_message}"""


def run_preop_response(
    *,
    patient_context: dict,
    retrieved_knowledge: list,
    recent_history: list[dict],
    user_message: str,
) -> str:
    prompt = ChatPromptTemplate.from_messages([
        ("system", _PREOP_SYSTEM),
        ("human", _PREOP_USER),
    ])
    chain = prompt | _get_llm(temperature=0.4) | StrOutputParser()

    postop_day = patient_context.get("postop_day", 0)
    days_until = abs(postop_day) if postop_day <= 0 else 0
    knowledge_str = _format_knowledge(retrieved_knowledge)

    try:
        result = chain.invoke({
            "patient_name": patient_context.get("name", ""),
            "days_until_surgery": days_until,
            "graft_type": patient_context.get("graft_type") or "unknown",
            "knowledge": knowledge_str,
            "recent_history": _format_history(recent_history),
            "user_message": user_message,
        })
        logger.info("preop_response_success")
        return result.strip()
    except Exception as e:
        logger.error("preop_response_failed", error=str(e))
        return (
            "Great question! Your surgical team will give you specific "
            "instructions during your pre-op appointment. Don't hesitate to "
            "write down any other questions you'd like to ask them."
        )
