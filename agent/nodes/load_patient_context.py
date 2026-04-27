"""
Node: load_patient_context

Fetches the patient record and builds a PatientContext dict for downstream nodes.
"""

from datetime import date

from agent.schemas import PatientContext
from agent.state import ACLWorkflowState
from repositories.patient import PatientRepository


def load_patient_context(state: ACLWorkflowState, *, db) -> dict:
    repo = PatientRepository(db)
    patient = repo.get(state["patient_id"])

    if patient is None:
        raise ValueError(f"Patient not found: {state['patient_id']}")

    surgery_date = patient.surgery_date
    if isinstance(surgery_date, str):
        surgery_date = date.fromisoformat(surgery_date)
    postop_day = max((date.today() - surgery_date).days, 0)

    ctx = PatientContext(
        patient_id=patient.patient_id,
        name=patient.name,
        phase=patient.phase,
        postop_day=postop_day,
        graft_type=patient.graft_type,
        protocol_id=patient.protocol_id,
    )

    return {"patient_context": ctx.model_dump()}
