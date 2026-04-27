"""
Node: run_rules

Runs the deterministic clinical rules engine against the current extraction.
Pre-op patients evaluate emergency symptoms only.
"""

import uuid

import structlog

from agent.rules import ExtractionInput, build_extraction_input, evaluate
from agent.state import ACLWorkflowState
from repositories.clinical_extraction import ClinicalExtractionRepository
from repositories.patient import PatientRepository
from repositories.rule_evaluation import RuleEvaluationRepository

logger = structlog.get_logger()


def run_rules(state: ACLWorkflowState, *, db) -> dict:
    patient_ctx = state["patient_context"]
    patient_id = state["patient_id"]

    if patient_ctx.get("phase") == "pre_op":
        extraction_result = state.get("extraction_result") or {}
        symptoms = extraction_result.get("symptoms", [])

        if "shortness_of_breath" in symptoms:
            logger.info(
                "run_rules_preop_emergency",
                patient_id=patient_id,
                rule="E1_shortness_of_breath_pe_risk",
            )
            return {
                "rule_result": {
                    "risk_level": "emergency",
                    "triggered_rules": ["E1_shortness_of_breath_pe_risk"],
                    "recommended_action": "call_911_immediately",
                    "escalation_needed": True,
                    "confidence": "high",
                    "clinician_summary": None,
                },
                "escalation_needed": True,
            }

        if "chest_pain" in symptoms:
            logger.info(
                "run_rules_preop_emergency",
                patient_id=patient_id,
                rule="E2_chest_pain_cardiac_or_pe",
            )
            return {
                "rule_result": {
                    "risk_level": "emergency",
                    "triggered_rules": ["E2_chest_pain_cardiac_or_pe"],
                    "recommended_action": "call_911_immediately",
                    "escalation_needed": True,
                    "confidence": "high",
                    "clinician_summary": None,
                },
                "escalation_needed": True,
            }

        logger.info("run_rules_skipped_preop", patient_id=patient_id)
        return {
            "rule_result": {
                "risk_level": "routine",
                "triggered_rules": [],
                "recommended_action": "continue_standard_protocol",
                "escalation_needed": False,
                "confidence": "high",
                "clinician_summary": None,
            },
            "escalation_needed": False,
        }

    ext_repo = ClinicalExtractionRepository(db)

    extraction_row = ext_repo.get_latest_by_patient(patient_id)
    extraction_id = extraction_row.extraction_id if extraction_row else ""

    if extraction_row is None:
        extraction_row_dict = state.get("extraction_result") or {}
    else:
        extraction_row_dict = {
            c.name: getattr(extraction_row, c.name)
            for c in extraction_row.__table__.columns
        }

    recent_rows = ext_repo.get_by_patient(patient_id, limit=5)
    recent_rows_dicts = [
        {c.name: getattr(r, c.name) for c in r.__table__.columns}
        for r in reversed(recent_rows)
    ]

    patient_repo = PatientRepository(db)
    patient_row = patient_repo.get(patient_id)
    patient_row_dict = (
        {c.name: getattr(patient_row, c.name) for c in patient_row.__table__.columns}
        if patient_row
        else patient_ctx
    )

    ext_input: ExtractionInput = build_extraction_input(
        extraction_row=extraction_row_dict,
        patient_row=patient_row_dict,
        recent_extractions=recent_rows_dicts,
    )

    result = evaluate(ext_input)

    try:
        rule_repo = RuleEvaluationRepository(db)
        rule_repo.create(
            evaluation_id=f"rule_{uuid.uuid4().hex[:12]}",
            extraction_id=extraction_id or None,
            patient_id=patient_id,
            risk_level=result.risk_level,
            triggered_rules=result.triggered_rules,
            recommended_action=result.recommended_action,
            escalation_needed=result.escalation_needed,
            confidence=result.confidence,
            clinician_summary=result.clinician_summary,
        )
        db.commit()
        logger.info(
            "rules_evaluated",
            patient_id=patient_id,
            risk_level=result.risk_level,
            escalation_needed=result.escalation_needed,
            triggered_rules=result.triggered_rules,
        )
    except Exception as e:
        logger.error("rule_save_failed", error=str(e))
        db.rollback()

    return {
        "rule_result": {
            "risk_level": result.risk_level,
            "triggered_rules": result.triggered_rules,
            "recommended_action": result.recommended_action,
            "escalation_needed": result.escalation_needed,
            "confidence": result.confidence,
            "clinician_summary": result.clinician_summary,
        },
        "escalation_needed": result.escalation_needed,
    }
