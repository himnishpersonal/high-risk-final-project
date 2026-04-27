"""
Node: clinical_extraction

Calls the LLM extraction chain to extract structured clinical data
from the patient message, then persists the result to the DB.
"""

import uuid

import structlog

from agent.chains import run_extraction
from agent.state import ACLWorkflowState
from repositories.clinical_extraction import ClinicalExtractionRepository

logger = structlog.get_logger()


def clinical_extraction(state: ACLWorkflowState, *, db) -> dict:
    ctx = state["patient_context"]

    result = run_extraction(
        user_message=state["user_message"],
        phase=ctx["phase"],
        postop_day=ctx["postop_day"],
        recent_history=state.get("recent_history", []),
    )

    result_dict = result.model_dump()

    try:
        repo = ClinicalExtractionRepository(db)
        repo.create(
            extraction_id=f"ext_{uuid.uuid4().hex[:12]}",
            event_id=state["conversation_event_id"],
            patient_id=state["patient_id"],
            intent=result.intent,
            symptoms=result.symptoms,
            symptoms_details=result.symptoms_details.model_dump(),
            ambiguity_status=result.ambiguity_status,
            missing_fields=result.missing_fields,
            references_prior=result.references_prior,
            postop_day=ctx.get("postop_day"),
        )
        db.commit()
        logger.info(
            "extraction_saved",
            patient_id=state["patient_id"],
            intent=result.intent,
        )
    except Exception as e:
        logger.error("extraction_save_failed", error=str(e))
        db.rollback()

    return {
        "extraction_result": result_dict,
        "ambiguity_status": result.ambiguity_status,
    }
