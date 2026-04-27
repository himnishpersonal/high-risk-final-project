import uuid
import structlog
from datetime import date, datetime
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI

from db.database import SessionLocal
from repositories.patient import PatientRepository
from repositories.conversation_event import ConversationEventRepository
from api.config import settings

logger = structlog.get_logger()

def _get_llm(temperature: float = 0.4) -> ChatOpenAI:
    return ChatOpenAI(
        model="gpt-5.4-mini",
        temperature=temperature,
        api_key=settings.openai_api_key,
    )


def phase_flip_job():
    db = SessionLocal()
    try:
        patient_repo = PatientRepository(db)
        today = date.today()
        
        all_active = patient_repo.get_active_patients(limit=1000)
        patients_to_flip = [
            p for p in all_active
            if p.surgery_date == today and p.phase == "pre_op"
        ]
        
        if not patients_to_flip:
            logger.info("phase_flip_job_no_patients", date=str(today))
            return
        
        flipped_count = 0
        for patient in patients_to_flip:
            patient_repo.update(
                patient.patient_id,
                phase="post_op",
                monitoring_start=datetime.now()
            )
            flipped_count += 1
            logger.info(
                "patient_flipped_to_postop",
                patient_id=patient.patient_id,
                patient_name=patient.name,
                surgery_date=str(patient.surgery_date)
            )
        
        db.commit()
        logger.info(
            "phase_flip_job_completed",
            flipped_count=flipped_count,
            date=str(today)
        )
    
    except Exception as e:
        db.rollback()
        logger.error("phase_flip_job_failed", error=str(e))
        raise
    
    finally:
        db.close()


PREOP_CHECKIN_PROMPT = ChatPromptTemplate.from_messages([
    ("system", """You are a friendly surgical coordinator checking in with a patient before ACL surgery.

Generate a warm, personalized check-in message that:
- Addresses the patient by name
- References how many days until surgery
- Asks a helpful prep question (e.g., about medications, logistics, questions, concerns)
- Feels supportive, not clinical
- Is 2-3 sentences max

Keep it conversational and encouraging."""),
    ("human", """Patient name: {patient_name}
Days until surgery: {days_until}

Generate a warm pre-op check-in message.""")
])

POSTOP_CHECKIN_PROMPT = ChatPromptTemplate.from_messages([
    ("system", """You are a caring surgical recovery coordinator checking in with a patient after ACL surgery.

Generate a warm, personalized check-in message that:
- Addresses the patient by name
- References their post-op day number
- Asks about their recovery symptoms (pain, swelling, mobility)
- Encourages them to report any concerns
- Feels supportive, not clinical
- Is 2-3 sentences max

Keep it conversational and caring."""),
    ("human", """Patient name: {patient_name}
Post-op day: {postop_day}

Generate a warm post-op check-in message.""")
])


def _generate_preop_checkin(patient_name: str, days_until: int) -> str:
    try:
        chain = PREOP_CHECKIN_PROMPT | _get_llm() | StrOutputParser()
        result = chain.invoke({
            "patient_name": patient_name,
            "days_until": days_until
        })
        return result.strip()
    except Exception as e:
        logger.error("preop_checkin_generation_failed", error=str(e))
        return (
            f"Hi {patient_name}! Just checking in as your surgery approaches. "
            f"Do you have any questions or concerns?"
        )


def _generate_postop_checkin(patient_name: str, postop_day: int) -> str:
    try:
        chain = POSTOP_CHECKIN_PROMPT | _get_llm() | StrOutputParser()
        result = chain.invoke({
            "patient_name": patient_name,
            "postop_day": postop_day
        })
        return result.strip()
    except Exception as e:
        logger.error("postop_checkin_generation_failed", error=str(e))
        return (
            f"Good morning {patient_name}! Day {postop_day} check-in. "
            f"How are you feeling today? Any pain, swelling, or concerns?"
        )


def daily_checkin_job():
    db = SessionLocal()
    try:
        patient_repo = PatientRepository(db)
        event_repo = ConversationEventRepository(db)
        today = date.today()
        
        all_active = patient_repo.get_active_patients(limit=1000)
        patients_in_window = [
            p for p in all_active
            if p.monitoring_start and p.monitoring_end
            and p.monitoring_start.date() <= today <= p.monitoring_end.date()
        ]
        
        if not patients_in_window:
            logger.info("daily_checkin_job_no_patients", date=str(today))
            return
        
        checkins_sent = 0
        
        for patient in patients_in_window:
            postop_day = (today - patient.surgery_date).days
            
            if postop_day == 0:
                logger.info(
                    "skipping_surgery_day_checkin",
                    patient_id=patient.patient_id,
                    patient_name=patient.name
                )
                continue
            
            if patient.phase == "pre_op":
                days_until = (patient.surgery_date - today).days
                message = _generate_preop_checkin(patient.name, days_until)
                phase = "pre_op"
                postop_day_val = None
            else:
                message = _generate_postop_checkin(patient.name, postop_day)
                phase = "post_op"
                postop_day_val = postop_day
            
            event_repo.create(
                event_id=f"evt_{uuid.uuid4().hex[:12]}",
                patient_id=patient.patient_id,
                role="system",
                message_text=message,
                phase=phase,
                postop_day=postop_day_val,
                status="sent"
            )
            
            checkins_sent += 1
            logger.info(
                "checkin_sent",
                patient_id=patient.patient_id,
                patient_name=patient.name,
                phase=phase,
                postop_day=postop_day_val
            )
        
        db.commit()
        logger.info(
            "daily_checkin_job_completed",
            checkins_sent=checkins_sent,
            date=str(today)
        )
    
    except Exception as e:
        db.rollback()
        logger.error("daily_checkin_job_failed", error=str(e))
        raise
    
    finally:
        db.close()


def close_monitoring_windows_job():
    db = SessionLocal()
    try:
        patient_repo = PatientRepository(db)
        today = date.today()
        
        all_active = patient_repo.get_active_patients(limit=1000)
        patients_to_close = [
            p for p in all_active
            if p.phase == "post_op"
            and p.monitoring_end
            and p.monitoring_end.date() < today
        ]
        
        if not patients_to_close:
            logger.info("close_monitoring_windows_no_patients", date=str(today))
            return
        
        closed_count = 0
        for patient in patients_to_close:
            patient_repo.update(
                patient.patient_id,
                status="completed"
            )
            closed_count += 1
            logger.info(
                "monitoring_window_closed",
                patient_id=patient.patient_id,
                patient_name=patient.name,
                monitoring_end=str(patient.monitoring_end.date())
            )
        
        db.commit()
        logger.info(
            "close_monitoring_windows_completed",
            closed_count=closed_count,
            date=str(today)
        )
    
    except Exception as e:
        db.rollback()
        logger.error("close_monitoring_windows_failed", error=str(e))
        raise
    
    finally:
        db.close()
