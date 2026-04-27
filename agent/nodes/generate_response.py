"""
Node: generate_response

Routes to the correct LLM response chain based on patient phase and risk level.
Saves clinician_summary to rule_evaluations for escalation cases.
"""

import structlog

from agent.chains import (
    run_escalation_response,
    run_preop_response,
    run_routine_response,
)
from agent.state import ACLWorkflowState
from repositories.rule_evaluation import RuleEvaluationRepository

logger = structlog.get_logger()


def generate_response(state: ACLWorkflowState, *, db) -> dict:
    patient_ctx = state.get("patient_context") or {}
    extraction_result = state.get("extraction_result") or {}
    rule_result = state.get("rule_result") or {}
    recent_history = state.get("recent_history") or []
    retrieved_knowledge = state.get("retrieved_knowledge") or []
    user_message = state.get("user_message", "")
    phase = patient_ctx.get("phase", "post_op")

    if rule_result.get("escalation_needed"):
        patient_msg, clinician_summary = run_escalation_response(
            patient_context=patient_ctx,
            extraction_result=extraction_result,
            rule_result=rule_result,
            retrieved_knowledge=retrieved_knowledge,
            recent_history=recent_history,
            user_message=user_message,
        )
        _save_clinician_summary(db, state, clinician_summary)
        return {"final_response": patient_msg}

    if phase == "pre_op":
        response = run_preop_response(
            patient_context=patient_ctx,
            retrieved_knowledge=retrieved_knowledge,
            recent_history=recent_history,
            user_message=user_message,
        )
        return {"final_response": response}

    response = run_routine_response(
        patient_context=patient_ctx,
        extraction_result=extraction_result,
        retrieved_knowledge=retrieved_knowledge,
        recent_history=recent_history,
        user_message=user_message,
    )
    return {"final_response": response}


def _save_clinician_summary(db, state: ACLWorkflowState, summary: str) -> None:
    """Persist clinician_summary to the most recent rule_evaluations row."""
    try:
        repo = RuleEvaluationRepository(db)
        evals = repo.get_by_patient(state["patient_id"], limit=1)
        if evals:
            repo.update(evals[0].evaluation_id, clinician_summary=summary)
            db.commit()
            logger.info("clinician_summary_saved", patient_id=state["patient_id"])
    except Exception as e:
        logger.error("clinician_summary_save_failed", error=str(e))
        db.rollback()
