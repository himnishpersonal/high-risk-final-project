"""
ClinicalExtraction repository for database operations related to clinical extractions.
"""
from typing import Optional, List
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from sqlalchemy import and_, desc

from db.models import ClinicalExtraction
from repositories.base import BaseRepository


class ClinicalExtractionRepository(BaseRepository[ClinicalExtraction]):
    
    def __init__(self, db: Session):
        super().__init__(db, ClinicalExtraction)
    
    def get_by_patient(
        self, patient_id: str, skip: int = 0, limit: int = 100
    ) -> List[ClinicalExtraction]:
        return (
            self.db.query(ClinicalExtraction)
            .filter(ClinicalExtraction.patient_id == patient_id)
            .order_by(desc(ClinicalExtraction.timestamp))
            .offset(skip)
            .limit(limit)
            .all()
        )
    
    def get_by_event(self, event_id: str) -> List[ClinicalExtraction]:
        return (
            self.db.query(ClinicalExtraction)
            .filter(ClinicalExtraction.event_id == event_id)
            .all()
        )
    
    def get_latest_by_patient(self, patient_id: str) -> Optional[ClinicalExtraction]:
        return (
            self.db.query(ClinicalExtraction)
            .filter(ClinicalExtraction.patient_id == patient_id)
            .order_by(desc(ClinicalExtraction.timestamp))
            .first()
        )
    
    def get_by_intent(
        self, intent: str, skip: int = 0, limit: int = 100
    ) -> List[ClinicalExtraction]:
        return (
            self.db.query(ClinicalExtraction)
            .filter(ClinicalExtraction.intent == intent)
            .order_by(desc(ClinicalExtraction.timestamp))
            .offset(skip)
            .limit(limit)
            .all()
        )
    
    def get_unclear_extractions(
        self, skip: int = 0, limit: int = 100
    ) -> List[ClinicalExtraction]:
        return (
            self.db.query(ClinicalExtraction)
            .filter(ClinicalExtraction.ambiguity_status == "unclear")
            .order_by(desc(ClinicalExtraction.timestamp))
            .offset(skip)
            .limit(limit)
            .all()
        )
    
    def get_by_symptom(
        self, symptom: str, patient_id: Optional[str] = None, skip: int = 0, limit: int = 100
    ) -> List[ClinicalExtraction]:
        query = self.db.query(ClinicalExtraction)
        
        if patient_id:
            query = query.filter(ClinicalExtraction.patient_id == patient_id)

        all_extractions = query.order_by(desc(ClinicalExtraction.timestamp)).all()
        filtered = [
            ex for ex in all_extractions
            if isinstance(ex.symptoms, list) and symptom in ex.symptoms
        ]
        
        return filtered[skip:skip + limit]
    
    def get_recent_by_patient_with_symptoms(
        self, patient_id: str, days: int = 7
    ) -> List[ClinicalExtraction]:
        
        cutoff_date = datetime.utcnow() - timedelta(days=days)
        extractions = (
            self.db.query(ClinicalExtraction)
            .filter(
                and_(
                    ClinicalExtraction.patient_id == patient_id,
                    ClinicalExtraction.timestamp >= cutoff_date
                )
            )
            .order_by(desc(ClinicalExtraction.timestamp))
            .all()
        )
        
        return [
            ex for ex in extractions
            if isinstance(ex.symptoms, list) and len(ex.symptoms) > 0
        ]
    
    def get_by_postop_day_range(
        self, min_day: int, max_day: int, skip: int = 0, limit: int = 100
    ) -> List[ClinicalExtraction]:
        return (
            self.db.query(ClinicalExtraction)
            .filter(
                and_(
                    ClinicalExtraction.postop_day.isnot(None),
                    ClinicalExtraction.postop_day >= min_day,
                    ClinicalExtraction.postop_day <= max_day
                )
            )
            .order_by(desc(ClinicalExtraction.timestamp))
            .offset(skip)
            .limit(limit)
            .all()
        )
