"""
API route definitions for the ACL Patient Assistant.
"""
from typing import Dict, Any
from fastapi import APIRouter, Depends, HTTPException, status, Form, Request
from sqlalchemy.orm import Session
from datetime import datetime

from db.database import get_db
from db.models import ConversationEvent, Patient
from repositories.patient import PatientRepository
from repositories.conversation_event import ConversationEventRepository
from api.sms import sms_service
from api.admin import router as admin_router

router = APIRouter()

router.include_router(admin_router)


@router.get("/health", tags=["system"])
async def health_check() -> Dict[str, str]:
    return {
        "status": "healthy",
        "service": "acl-patient-assistant",
        "version": "0.1.0"
    }


@router.get("/patients/{patient_id}", tags=["patients"])
async def get_patient(
    patient_id: str,
    db: Session = Depends(get_db)
) -> Dict[str, Any]:
    
    repo = PatientRepository(db)
    patient = repo.get(patient_id)
    
    if not patient:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Patient with ID {patient_id} not found"
        )
    
    return {
        "patient_id": patient.patient_id,
        "name": patient.name,
        "phone": patient.phone,
        "age": patient.age,
        "phase": patient.phase,
        "status": patient.status,
        "surgery_date": patient.surgery_date.isoformat(),
        "graft_type": patient.graft_type,
        "protocol_id": patient.protocol_id,
    }


@router.get("/patients", tags=["patients"])
async def list_patients(
    phase: str = None,
    patient_status: str = None,
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db)
) -> Dict[str, Any]:
    
    from fastapi import status as http_status
    
    repo = PatientRepository(db)
    
    if phase:
        if phase not in ("pre_op", "post_op"):
            raise HTTPException(
                status_code=http_status.HTTP_400_BAD_REQUEST,
                detail="Phase must be 'pre_op' or 'post_op'"
            )
        patients = repo.get_by_phase(phase, skip=skip, limit=limit)
    elif patient_status:
        if patient_status not in ("active", "completed", "discharged"):
            raise HTTPException(
                status_code=http_status.HTTP_400_BAD_REQUEST,
                detail="Status must be 'active', 'completed', or 'discharged'"
            )
        patients = repo.get_by_status(patient_status, skip=skip, limit=limit)
    else:
        patients = repo.get_all(skip=skip, limit=limit)
    
    patient_list = [
        {
            "patient_id": p.patient_id,
            "name": p.name,
            "phone": p.phone,
            "phase": p.phase,
            "status": p.status,
            "surgery_date": p.surgery_date.isoformat(),
        }
        for p in patients
    ]
    
    return {
        "patients": patient_list,
        "count": len(patient_list),
        "skip": skip,
        "limit": limit,
    }


@router.post("/webhook/sms", tags=["webhooks"])
async def receive_sms(
    request: Request,
    From: str = Form(...),
    Body: str = Form(...),
    MessageSid: str = Form(...),
    db: Session = Depends(get_db)
) -> Dict[str, str]:

    import structlog
    logger = structlog.get_logger()
    
    logger.info(
        "sms_received",
        from_phone=From,
        message_sid=MessageSid,
        body_length=len(Body)
    )
    
    patient_repo = PatientRepository(db)
    patient = patient_repo.get_by_phone(From)

    if not patient:
        logger.warning("patient_not_found", from_phone=From)
        sms_service.send_message(
            to_phone=From,
            body="Sorry, we couldn't find your record. Please contact your care team."
        )
        return {"status": "patient_not_found"}

    from agent.workflow import run_acl_workflow

    final_state = run_acl_workflow(
        patient_id=patient.patient_id,
        user_message=Body,
        db=db,
    )

    response_body = final_state.get(
        "final_response",
        "We received your message. Your care team will follow up shortly.",
    )

    message_sid = sms_service.send_message(to_phone=From, body=response_body)

    if message_sid:
        event_repo = ConversationEventRepository(db)
        event_repo.update(
            final_state.get("conversation_event_id", ""),
            twilio_sid=MessageSid,
        )

    return {"status": "success"}


@router.post("/webhook/sms/status", tags=["webhooks"])
async def sms_status_callback(
    MessageSid: str = Form(...),
    MessageStatus: str = Form(...),
    db: Session = Depends(get_db)
) -> Dict[str, str]:
    
    import structlog
    logger = structlog.get_logger()
    
    logger.info(
        "sms_status_update",
        message_sid=MessageSid,
        status=MessageStatus
    )
    
    event_repo = ConversationEventRepository(db)
    event = event_repo.get_by_twilio_sid(MessageSid)
    
    if event:
        event_repo.update_delivery_status(MessageSid, MessageStatus)
        logger.info(
            "delivery_status_updated",
            event_id=event.event_id,
            status=MessageStatus
        )
    else:
        logger.warning("message_not_found", message_sid=MessageSid)
    
    return {"status": "received"}


