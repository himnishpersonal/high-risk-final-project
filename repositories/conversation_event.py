"""
ConversationEvent repository for database operations related to conversation events.
"""
from typing import Optional, List
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from sqlalchemy import and_, desc

from db.models import ConversationEvent
from repositories.base import BaseRepository


class ConversationEventRepository(BaseRepository[ConversationEvent]):
    
    def __init__(self, db: Session):
        super().__init__(db, ConversationEvent)
    
    def get_by_patient(
        self, patient_id: str, skip: int = 0, limit: int = 100
    ) -> List[ConversationEvent]:
        return (
            self.db.query(ConversationEvent)
            .filter(ConversationEvent.patient_id == patient_id)
            .order_by(desc(ConversationEvent.timestamp))
            .offset(skip)
            .limit(limit)
            .all()
        )
    
    def get_recent_by_patient(
        self, patient_id: str, limit: int = 10
    ) -> List[ConversationEvent]:
        return self.get_by_patient(patient_id, skip=0, limit=limit)
    
    def get_by_patient_and_role(
        self, patient_id: str, role: str, skip: int = 0, limit: int = 100
    ) -> List[ConversationEvent]:
        return (
            self.db.query(ConversationEvent)
            .filter(
                and_(
                    ConversationEvent.patient_id == patient_id,
                    ConversationEvent.role == role
                )
            )
            .order_by(desc(ConversationEvent.timestamp))
            .offset(skip)
            .limit(limit)
            .all()
        )
    
    def get_by_twilio_sid(self, twilio_sid: str) -> Optional[ConversationEvent]:
        return (
            self.db.query(ConversationEvent)
            .filter(ConversationEvent.twilio_sid == twilio_sid)
            .first()
        )
    
    def update_delivery_status(
        self, event_id: str, delivery_status: str
    ) -> Optional[ConversationEvent]:
        return self.update(event_id, delivery_status=delivery_status)
    
    def get_pending_delivery(self, skip: int = 0, limit: int = 100) -> List[ConversationEvent]:
        return (
            self.db.query(ConversationEvent)
            .filter(
                and_(
                    ConversationEvent.twilio_sid.isnot(None),
                    ConversationEvent.delivery_status.is_(None)
                )
            )
            .order_by(ConversationEvent.timestamp)
            .offset(skip)
            .limit(limit)
            .all()
        )
    
    def get_failed_deliveries(
        self, hours: int = 24, skip: int = 0, limit: int = 100
    ) -> List[ConversationEvent]:
        cutoff_time = datetime.utcnow() - timedelta(hours=hours)
        return (
            self.db.query(ConversationEvent)
            .filter(
                and_(
                    ConversationEvent.delivery_status == "failed",
                    ConversationEvent.timestamp >= cutoff_time
                )
            )
            .order_by(desc(ConversationEvent.timestamp))
            .offset(skip)
            .limit(limit)
            .all()
        )
    
    def get_by_phase(
        self, phase: str, skip: int = 0, limit: int = 100
    ) -> List[ConversationEvent]:
        return (
            self.db.query(ConversationEvent)
            .filter(ConversationEvent.phase == phase)
            .order_by(desc(ConversationEvent.timestamp))
            .offset(skip)
            .limit(limit)
            .all()
        )
    
    def get_conversation_history(
        self, patient_id: str, max_messages: int = 10
    ) -> List[ConversationEvent]:
        events = (
            self.db.query(ConversationEvent)
            .filter(
                and_(
                    ConversationEvent.patient_id == patient_id,
                    ConversationEvent.role.in_(["patient", "agent"])
                )
            )
            .order_by(desc(ConversationEvent.timestamp))
            .limit(max_messages)
            .all()
        )
        return list(reversed(events))
