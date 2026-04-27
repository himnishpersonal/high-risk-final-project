from sqlalchemy import Boolean, CheckConstraint, Column, Date, ForeignKey, Integer, Text, TIMESTAMP, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship
from sqlalchemy.types import JSON

from db.database import Base

JsonColumn = JSONB().with_variant(JSON(), "sqlite")

class Patient(Base):
    __tablename__ = "patients"

    patient_id = Column(Text, primary_key=True)
    name = Column(Text, nullable=False)
    age = Column(Integer, nullable=False)
    weight = Column(Integer, nullable=False)
    height = Column(Integer, nullable=False)
    phone = Column(Text, nullable=False)
    surgery_date = Column(Date, nullable=False)
    phase = Column(Text, nullable=False)
    graft_type = Column(Text, nullable=True)
    protocol_id = Column(Text, nullable=True)
    status = Column(Text, nullable=False, default="active")
    last_contact = Column(TIMESTAMP, nullable=True)
    monitoring_start = Column(TIMESTAMP, nullable=True)
    monitoring_end = Column(TIMESTAMP, nullable=True)
    created_at = Column(TIMESTAMP, nullable=False, server_default=func.now())
    updated_at = Column(TIMESTAMP, nullable=False, server_default=func.now(), onupdate=func.now())

    conversation_events = relationship("ConversationEvent", back_populates="patient")
    clinical_extractions = relationship("ClinicalExtraction", back_populates="patient")
    rule_evaluations = relationship("RuleEvaluation", back_populates="patient")

    __table_args__ = (
        CheckConstraint("phase IN ('pre_op', 'post_op')", name="ck_patients_phase"),
        CheckConstraint("status IN ('active', 'completed', 'discharged')", name="ck_patients_status"),
    )


class ConversationEvent(Base):
    __tablename__ = "conversation_events"

    event_id = Column(Text, primary_key=True)
    patient_id = Column(Text, ForeignKey("patients.patient_id"), nullable=False)
    role = Column(Text, nullable=False)
    message_text = Column(Text, nullable=False)
    phase = Column(Text, nullable=False)
    postop_day = Column(Integer, nullable=True)
    status = Column(Text, nullable=False)
    twilio_sid = Column(Text, nullable=True)
    delivery_status = Column(Text, nullable=True)
    timestamp = Column(TIMESTAMP, nullable=False, server_default=func.now())

    patient = relationship("Patient", back_populates="conversation_events")
    clinical_extractions = relationship("ClinicalExtraction", back_populates="event")

    __table_args__ = (
        CheckConstraint("role IN ('system', 'patient', 'agent')", name="ck_conversation_events_role"),
        CheckConstraint("phase IN ('pre_op', 'post_op')", name="ck_conversation_events_phase"),
    )


class ClinicalExtraction(Base):
    __tablename__ = "clinical_extractions"

    extraction_id = Column(Text, primary_key=True)
    event_id = Column(Text, ForeignKey("conversation_events.event_id"), nullable=False)
    patient_id = Column(Text, ForeignKey("patients.patient_id"), nullable=False)
    intent = Column(Text, nullable=False)
    symptoms = Column(JsonColumn, nullable=False)
    symptoms_details = Column(JsonColumn, nullable=False)
    ambiguity_status = Column(Text, nullable=False)
    missing_fields = Column(JsonColumn, nullable=False)
    references_prior = Column(Boolean, nullable=False)
    postop_day = Column(Integer, nullable=True)
    timestamp = Column(TIMESTAMP, nullable=False, server_default=func.now())

    patient = relationship("Patient", back_populates="clinical_extractions")
    event = relationship("ConversationEvent", back_populates="clinical_extractions")
    rule_evaluations = relationship("RuleEvaluation", back_populates="extraction")

    __table_args__ = (
        CheckConstraint("ambiguity_status IN ('clear', 'unclear')", name="ck_clinical_extractions_ambiguity_status"),
    )


class RuleEvaluation(Base):
    __tablename__ = "rule_evaluations"

    evaluation_id = Column(Text, primary_key=True)
    extraction_id = Column(Text, ForeignKey("clinical_extractions.extraction_id"), nullable=False)
    patient_id = Column(Text, ForeignKey("patients.patient_id"), nullable=False)
    risk_level = Column(Text, nullable=False)
    triggered_rules = Column(JsonColumn, nullable=False)
    recommended_action = Column(Text, nullable=False)
    escalation_needed = Column(Boolean, nullable=False)
    confidence = Column(Text, nullable=False)
    clinician_summary = Column(Text, nullable=True)
    escalated_to = Column(Text, nullable=True)
    escalation_sent_at = Column(TIMESTAMP, nullable=True)
    timestamp = Column(TIMESTAMP, nullable=False, server_default=func.now())

    patient = relationship("Patient", back_populates="rule_evaluations")
    extraction = relationship("ClinicalExtraction", back_populates="rule_evaluations")

    __table_args__ = (
        CheckConstraint(
            "risk_level IN ('routine', 'medium', 'high', 'emergency')",
            name="ck_rule_evaluations_risk_level",
        ),
        CheckConstraint("confidence IN ('high', 'low')", name="ck_rule_evaluations_confidence"),
    )
