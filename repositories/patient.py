"""
Patient repository for database operations related to patients.
"""
from typing import Optional, List
from datetime import datetime, date
from sqlalchemy.orm import Session
from sqlalchemy import and_, or_

from db.models import Patient
from repositories.base import BaseRepository


class PatientRepository(BaseRepository[Patient]):

    def __init__(self, db: Session):
        super().__init__(db, Patient)
    
    def get_by_phone(self, phone: str) -> Optional[Patient]:
        return self.db.query(Patient).filter(Patient.phone == phone).first()
    
    def get_by_status(self, status: str, skip: int = 0, limit: int = 100) -> List[Patient]:
        return (
            self.db.query(Patient)
            .filter(Patient.status == status)
            .offset(skip)
            .limit(limit)
            .all()
        )
    
    def get_by_phase(self, phase: str, skip: int = 0, limit: int = 100) -> List[Patient]:
        return (
            self.db.query(Patient)
            .filter(Patient.phase == phase)
            .offset(skip)
            .limit(limit)
            .all()
        )
    
    def get_active_patients(self, skip: int = 0, limit: int = 100) -> List[Patient]:
        return self.get_by_status("active", skip, limit)
    
    def get_patients_needing_contact(
        self, days_since_contact: int = 7, skip: int = 0, limit: int = 100
    ) -> List[Patient]:
        cutoff_date = datetime.utcnow() - datetime.timedelta(days=days_since_contact)
        return (
            self.db.query(Patient)
            .filter(
                and_(
                    Patient.status == "active",
                    or_(
                        Patient.last_contact.is_(None),
                        Patient.last_contact < cutoff_date
                    )
                )
            )
            .offset(skip)
            .limit(limit)
            .all()
        )
    
    def update_last_contact(self, patient_id: str) -> Optional[Patient]:
        return self.update(patient_id, last_contact=datetime.utcnow())
    
    def advance_to_phase(self, patient_id: str, phase: str) -> Optional[Patient]:
        return self.update(patient_id, phase=phase)
    
    def get_by_surgery_date_range(
        self, start_date: date, end_date: date, skip: int = 0, limit: int = 100
    ) -> List[Patient]:
        return (
            self.db.query(Patient)
            .filter(
                and_(
                    Patient.surgery_date >= start_date,
                    Patient.surgery_date <= end_date
                )
            )
            .offset(skip)
            .limit(limit)
            .all()
        )
