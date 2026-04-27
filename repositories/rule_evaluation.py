"""
RuleEvaluation repository for database operations related to rule evaluations.
"""
from typing import Optional, List
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from sqlalchemy import and_, desc

from db.models import RuleEvaluation
from repositories.base import BaseRepository


class RuleEvaluationRepository(BaseRepository[RuleEvaluation]):

    def __init__(self, db: Session):
        super().__init__(db, RuleEvaluation)
    
    def get_by_patient(
        self, patient_id: str, skip: int = 0, limit: int = 100
    ) -> List[RuleEvaluation]:
        return (
            self.db.query(RuleEvaluation)
            .filter(RuleEvaluation.patient_id == patient_id)
            .order_by(desc(RuleEvaluation.timestamp))
            .offset(skip)
            .limit(limit)
            .all()
        )
    
    def get_by_extraction(self, extraction_id: str) -> Optional[RuleEvaluation]:
        return (
            self.db.query(RuleEvaluation)
            .filter(RuleEvaluation.extraction_id == extraction_id)
            .first()
        )
    
    def get_by_risk_level(
        self, risk_level: str, skip: int = 0, limit: int = 100
    ) -> List[RuleEvaluation]:
        return (
            self.db.query(RuleEvaluation)
            .filter(RuleEvaluation.risk_level == risk_level)
            .order_by(desc(RuleEvaluation.timestamp))
            .offset(skip)
            .limit(limit)
            .all()
        )
    
    def get_escalations(
        self, skip: int = 0, limit: int = 100
    ) -> List[RuleEvaluation]:
        return (
            self.db.query(RuleEvaluation)
            .filter(RuleEvaluation.escalation_needed == True)
            .order_by(desc(RuleEvaluation.timestamp))
            .offset(skip)
            .limit(limit)
            .all()
        )
    
    def get_recent_escalations(
        self, hours: int = 24, skip: int = 0, limit: int = 100
    ) -> List[RuleEvaluation]:
        cutoff_time = datetime.utcnow() - timedelta(hours=hours)
        return (
            self.db.query(RuleEvaluation)
            .filter(
                and_(
                    RuleEvaluation.escalation_needed == True,
                    RuleEvaluation.timestamp >= cutoff_time
                )
            )
            .order_by(desc(RuleEvaluation.timestamp))
            .offset(skip)
            .limit(limit)
            .all()
        )
    
    def get_unescalated(self, skip: int = 0, limit: int = 100) -> List[RuleEvaluation]:
        return (
            self.db.query(RuleEvaluation)
            .filter(
                and_(
                    RuleEvaluation.escalation_needed == True,
                    RuleEvaluation.escalated_to.is_(None)
                )
            )
            .order_by(RuleEvaluation.timestamp)
            .offset(skip)
            .limit(limit)
            .all()
        )
    
    def mark_escalated(
        self, evaluation_id: str, escalated_to: str
    ) -> Optional[RuleEvaluation]:
        return self.update(
            evaluation_id,
            escalated_to=escalated_to,
            escalation_sent_at=datetime.utcnow()
        )
    
    def get_by_triggered_rule(
        self, rule_id: str, skip: int = 0, limit: int = 100
    ) -> List[RuleEvaluation]:
        all_evaluations = (
            self.db.query(RuleEvaluation)
            .order_by(desc(RuleEvaluation.timestamp))
            .all()
        )
        filtered = [
            ev for ev in all_evaluations
            if isinstance(ev.triggered_rules, list) and rule_id in ev.triggered_rules
        ]
        
        return filtered[skip:skip + limit]
    
    def get_high_risk_for_patient(
        self, patient_id: str, days: int = 7
    ) -> List[RuleEvaluation]:
        cutoff_date = datetime.utcnow() - timedelta(days=days)
        return (
            self.db.query(RuleEvaluation)
            .filter(
                and_(
                    RuleEvaluation.patient_id == patient_id,
                    RuleEvaluation.risk_level.in_(["high", "emergency"]),
                    RuleEvaluation.timestamp >= cutoff_date
                )
            )
            .order_by(desc(RuleEvaluation.timestamp))
            .all()
        )
    
    def get_low_confidence_evaluations(
        self, skip: int = 0, limit: int = 100
    ) -> List[RuleEvaluation]:
        return (
            self.db.query(RuleEvaluation)
            .filter(RuleEvaluation.confidence == "low")
            .order_by(desc(RuleEvaluation.timestamp))
            .offset(skip)
            .limit(limit)
            .all()
        )
