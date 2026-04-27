"""
Pydantic v2 schemas for the LLM / agent layer.
"""

from typing import Literal, Optional
from pydantic import BaseModel, Field, field_validator


ALLOWED_SYMPTOMS = frozenset(
    {
        "swelling",
        "warmth",
        "redness",
        "drainage",
        "calf_pain",
        "calf_swelling",
        "fever",
        "chest_pain",
        "shortness_of_breath",
        "pain",
    }
)

ALLOWED_INTENTS = frozenset(
    {
        "postop_symptom_check",
        "preop_question",
        "activity_question",
        "general_concern",
    }
)

class SymptomsDetails(BaseModel):

    location: Optional[str] = Field(
        default=None,
        description="Anatomical location (e.g. 'knee', 'calf', 'thigh', 'general').",
    )
    severity_score: Optional[int] = Field(
        default=None,
        ge=0,
        le=10,
        description="Patient-reported pain severity on a 0–10 VAS scale.",
    )
    trend: Literal["worsening", "stable", "improving", "unknown"] = Field(
        default="unknown",
        description="Direction of symptom change since last report.",
    )

class ClinicalExtractionResult(BaseModel):

    intent: Literal[
        "postop_symptom_check",
        "preop_question",
        "activity_question",
        "general_concern",
    ] = Field(description="Clinically relevant intent of the patient message.")

    symptoms: list[
        Literal[
            "swelling",
            "warmth",
            "redness",
            "drainage",
            "calf_pain",
            "calf_swelling",
            "fever",
            "chest_pain",
            "shortness_of_breath",
            "pain",
        ]
    ] = Field(
        default_factory=list,
        description="Symptoms explicitly mentioned or strongly implied by the patient.",
    )

    symptoms_details: SymptomsDetails = Field(
        default_factory=SymptomsDetails,
        description="Structured detail for the reported symptom cluster.",
    )

    ambiguity_status: Literal["clear", "unclear"] = Field(
        description=(
            "'clear' if the extraction is confident. "
            "'unclear' if key clinical fields are missing or contradictory."
        )
    )

    missing_fields: list[str] = Field(
        default_factory=list,
        description=(
            "Names of fields the LLM could not populate due to insufficient "
            "patient input (e.g. 'pain_severity', 'fever', 'calf_pain')."
        ),
    )

    references_prior: bool = Field(
        default=False,
        description="True if the patient explicitly references a prior message or visit.",
    )

    @field_validator("symptoms")
    @classmethod
    def symptoms_must_be_known(cls, v: list[str]) -> list[str]:
        unknown = set(v) - ALLOWED_SYMPTOMS
        if unknown:
            raise ValueError(
                f"Unknown symptom(s): {unknown}. "
                f"Allowed: {sorted(ALLOWED_SYMPTOMS)}"
            )
        return list(dict.fromkeys(v))  # deduplicate, preserve order


class RuleEvaluationResult(BaseModel):

    risk_level: Literal["routine", "medium", "high", "emergency"] = Field(
        description="Triage severity determined by the rules engine."
    )

    triggered_rules: list[str] = Field(
        default_factory=list,
        description="IDs of every rule that fired (e.g. 'H1_calf_pain_dvt_risk').",
    )

    recommended_action: str = Field(
        description="Plain-English next step for the care team or patient."
    )

    escalation_needed: bool = Field(
        description="True when risk_level is medium, high, or emergency."
    )

    confidence: Literal["high", "low"] = Field(
        description=(
            "'low' when a triggered rule depended on a field that was missing "
            "from the extraction (signals uncertainty to the LLM response node)."
        )
    )

    clinician_summary: Optional[str] = Field(
        default=None,
        description=(
            "LLM-generated plain-English summary for the on-call clinician. "
            "Populated only when escalation_needed is True."
        ),
    )

class PatientContext(BaseModel):

    patient_id: str = Field(description="Unique patient identifier.")

    name: str = Field(description="Patient's full name.")

    phase: Literal["pre_op", "post_op"] = Field(
        description="Current care phase."
    )

    postop_day: int = Field(
        ge=0,
        description=(
            "Number of days since surgery. "
            "0 on surgery day. Negative values not permitted."
        ),
    )

    graft_type: Optional[str] = Field(
        default=None,
        description="ACL graft type (e.g. 'hamstring', 'patellar', 'allograft').",
    )

    protocol_id: Optional[str] = Field(
        default=None,
        description="Rehabilitation protocol identifier for knowledge-base retrieval.",
    )
