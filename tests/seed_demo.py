"""
Demo seed script.

Usage:
    python tests/seed_demo.py
"""

import sys
import uuid
from datetime import date, timedelta

sys.path.insert(0, ".")

from db.database import SessionLocal
from db.models import ClinicalExtraction, ConversationEvent, Patient, RuleEvaluation

DEMO_PATIENTS = [
    {
        "phone": "+15550000001",
        "name": "Sarah Johnson",
        "age": 28,
        "weight": 145,
        "height": 65,
        "surgery_date": date.today() - timedelta(days=5),
        "phase": "post_op",
        "graft_type": "patellar",
        "protocol_id": "acl_standard_v2",
        "status": "active",
        "monitoring_start": date.today() - timedelta(days=5),
        "monitoring_end": date.today() + timedelta(days=9),
    },
    {
        "phone": "+15550000002",
        "name": "Marcus Williams",
        "age": 24,
        "weight": 180,
        "height": 71,
        "surgery_date": date.today() + timedelta(days=7),
        "phase": "pre_op",
        "graft_type": "hamstring",
        "protocol_id": "acl_standard_v2",
        "status": "active",
        "monitoring_start": date.today(),
        "monitoring_end": date.today() + timedelta(days=21),
    },
]


def _clear_patient_data(db, patient_id: str) -> None:
    db.query(RuleEvaluation).filter(RuleEvaluation.patient_id == patient_id).delete()
    db.query(ClinicalExtraction).filter(ClinicalExtraction.patient_id == patient_id).delete()
    db.query(ConversationEvent).filter(ConversationEvent.patient_id == patient_id).delete()


def seed() -> None:
    db = SessionLocal()
    try:
        seeded = []

        for spec in DEMO_PATIENTS:
            phone = spec["phone"]
            existing = db.query(Patient).filter(Patient.phone == phone).first()

            if existing:
                _clear_patient_data(db, existing.patient_id)
                for field, value in spec.items():
                    if field != "phone":
                        setattr(existing, field, value)
                patient = existing
                action = "refreshed"
            else:
                patient = Patient(patient_id=str(uuid.uuid4()), **spec)
                db.add(patient)
                action = "created"

            db.flush()
            seeded.append((patient, action))

        db.commit()

        print("\nDemo patients ready:")
        print("-" * 50)
        for patient, action in seeded:
            print(
                f"  [{action}]  {patient.name}"
                f"  |  {patient.phase}"
                f"  |  phone: {patient.phone}"
            )
            print(f"             patient_id: {patient.patient_id}")
        print()
        print("Next step:")
        print("  streamlit run app/streamlit_app.py")

    finally:
        db.close()


if __name__ == "__main__":
    seed()
