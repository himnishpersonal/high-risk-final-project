"""
Clinical Sources Referenced

[CDC-NHSN]   Centers for Disease Control and Prevention. National Healthcare
             Safety Network (NHSN) Patient Safety Component Manual, Chapter 9:
             Surgical Site Infection (SSI) Event. 2024.
             https://www.cdc.gov/nhsn/pdfs/pscmanual/9pscssicurrent.pdf

[ACC-AHA]    Kearon C, et al. Antithrombotic Therapy for VTE Disease: CHEST
             Guideline and Expert Panel Report. American College of Chest
             Physicians. 2016. DOI: 10.1016/j.chest.2015.11.026
             Also: 2023 ACC/AHA Guideline on Diagnosis and Management of
             Atrial Fibrillation — PE/DVT post-surgical section.
             https://www.ahajournals.org/doi/10.1161/CIR.0000000000000769

[WELLS]      Wells PS, et al. Evaluation of D-dimer in the diagnosis of
             suspected deep-vein thrombosis. NEJM. 2003;349(13):1227-35.
             DOI: 10.1056/NEJMoa023153
             MDCalc implementation: https://www.mdcalc.com/calc/362/wells-criteria-dvt

[AAOS-ACL]   American Academy of Orthopaedic Surgeons. Management of Anterior
             Cruciate Ligament Injuries: Evidence-Based Clinical Practice
             Guideline. 2022.
             https://www.aaos.org/globalassets/quality-and-practice-resources/
             anterior-cruciate-ligament-injuries/aclcpg.pdf

[AAOS-PAIN]  AAOS ACL CPG Section 4.1 — Postoperative Pain Management.
             Expected VAS pain score by postop day range.

[NHS-DVT]    NHS Scotland. Wells DVT Score — Clinical Decision Tool. 2020.
             https://www.knowledge.scot.nhs.uk/media/CLT/ResourceUploads/
             4098256/e8280c09-132e-49d2-a5d1-37b8f80e869c.pdf
"""

from dataclasses import dataclass, field
from typing import Optional

@dataclass
class RuleEvaluation:
    risk_level: str
    triggered_rules: list[str]
    recommended_action: str
    escalation_needed: bool           
    confidence: str          
    clinician_summary: Optional[str] = None

@dataclass
class ExtractionInput:

    patient_id: str
    postop_day: int

    symptoms: list[str] = field(default_factory=list)

    pain_severity: Optional[int] = None
    symptom_trend: Optional[str] = None
    symptom_location: Optional[str] = None

    has_calf_pain: bool = False
    has_calf_swelling: bool = False
    has_fever: bool = False
    has_redness: bool = False
    has_warmth: bool = False
    has_drainage: bool = False
    has_chest_pain: bool = False
    has_shortness_of_breath: bool = False
    has_swelling: bool = False
    has_pain: bool = False

    ambiguity_status: str = "clear"
    missing_fields: list[str] = field(default_factory=list)
    references_prior: bool = False

    recent_symptom_history: list[list[str]] = field(default_factory=list)

RISK_ROUTINE   = "routine"
RISK_MEDIUM    = "medium"
RISK_HIGH      = "high"
RISK_EMERGENCY = "emergency"

ACTION_CONTINUE   = "continue_standard_protocol"
ACTION_MONITOR    = "monitor_closely_next_24h"
ACTION_CLINICIAN  = "contact_clinician_today"
ACTION_URGENT     = "urgent_evaluation_needed"
ACTION_911        = "call_911_immediately"

def _resolve_symptom_flags(ext: ExtractionInput) -> None:
    """
    Populate boolean flags from the symptoms list.
    Called once at the start of evaluate().
    """
    s = [sym.lower() for sym in ext.symptoms]
    ext.has_calf_pain           = "calf_pain"            in s
    ext.has_calf_swelling       = "calf_swelling"        in s
    ext.has_fever               = "fever"                in s
    ext.has_redness             = "redness"              in s
    ext.has_warmth              = "warmth"               in s
    ext.has_drainage            = "drainage"             in s
    ext.has_chest_pain          = "chest_pain"           in s
    ext.has_shortness_of_breath = "shortness_of_breath"  in s
    ext.has_swelling            = "swelling"             in s
    ext.has_pain                = "pain"                 in s

def _assess_confidence(ext: ExtractionInput, triggered_rules: list[str]) -> str:

    if not triggered_rules:
        return "high"

    critical_missing = []

    if any("dvt" in r or "calf" in r for r in triggered_rules):
        if "calf_pain" in ext.missing_fields or "calf_swelling" in ext.missing_fields:
            critical_missing.append("calf symptoms")

    if any("ssi" in r or "infection" in r for r in triggered_rules):
        if "fever" in ext.missing_fields:
            critical_missing.append("fever status")

    if any("pain" in r for r in triggered_rules):
        if "pain_severity" in ext.missing_fields or ext.pain_severity is None:
            critical_missing.append("pain score")

    return "low" if critical_missing else "high"

def _detect_worsening_trend(
    current_symptoms: list[str],
    recent_history: list[list[str]],
    min_occurrences: int = 2
) -> list[str]:

    if not recent_history:
        return []

    current_set = set(s.lower() for s in current_symptoms)
    trend_symptoms = []

    for symptom in current_set:
        count = sum(
            1 for prior_symptoms in recent_history
            if symptom in [s.lower() for s in prior_symptoms]
        )
        if count >= min_occurrences:
            trend_symptoms.append(symptom)

    return trend_symptoms

def evaluate(ext: ExtractionInput) -> RuleEvaluation:

    _resolve_symptom_flags(ext)

    triggered_rules: list[str] = []
    risk_level = RISK_ROUTINE
    recommended_action = ACTION_CONTINUE

    # Rule E1 — Pulmonary Embolism Warning
    if ext.has_shortness_of_breath:
        triggered_rules.append("E1_shortness_of_breath_pe_risk")
        return RuleEvaluation(
            risk_level=RISK_EMERGENCY,
            triggered_rules=triggered_rules,
            recommended_action=ACTION_911,
            escalation_needed=True,
            confidence="high",
        )

    # Rule E2 — Chest Pain
    if ext.has_chest_pain:
        triggered_rules.append("E2_chest_pain_cardiac_or_pe")
        return RuleEvaluation(
            risk_level=RISK_EMERGENCY,
            triggered_rules=triggered_rules,
            recommended_action=ACTION_911,
            escalation_needed=True,
            confidence="high",
        )

    # Rule H1 — DVT Risk: Calf Pain
    if ext.has_calf_pain:
        triggered_rules.append("H1_calf_pain_dvt_risk")
        risk_level = RISK_HIGH
        recommended_action = ACTION_CLINICIAN

    # Rule H2 — DVT Risk: Calf Swelling
    if ext.has_calf_swelling:
        triggered_rules.append("H2_calf_swelling_dvt_risk")
        risk_level = RISK_HIGH
        recommended_action = ACTION_CLINICIAN

    # Rule H3 — Surgical Site Infection (SSI)
    if ext.has_fever and (ext.has_redness or ext.has_warmth or ext.has_drainage):
        triggered_rules.append("H3_fever_plus_local_signs_ssi_risk")
        risk_level = RISK_HIGH
        recommended_action = ACTION_CLINICIAN

    # Rule H4 — Drainage Without Fever (Possible SSI)
    if ext.has_drainage and not ext.has_fever:
        triggered_rules.append("H4_drainage_without_fever_ssi_possible")
        if risk_level == RISK_ROUTINE:
            risk_level = RISK_HIGH
            recommended_action = ACTION_CLINICIAN

    # Rule H5 — Uncontrolled Pain Past Acute Phase
    if (
        ext.pain_severity is not None
        and ext.pain_severity >= 8
        and ext.postop_day > 5
    ):
        triggered_rules.append("H5_uncontrolled_pain_past_acute_phase")
        if risk_level == RISK_ROUTINE:
            risk_level = RISK_HIGH
            recommended_action = ACTION_CLINICIAN

    # Rule M1 — Worsening Trend Across Multiple Days
    trending = _detect_worsening_trend(
        ext.symptoms,
        ext.recent_symptom_history,
        min_occurrences=2
    )
    if trending and risk_level == RISK_ROUTINE:
        triggered_rules.append(f"M1_worsening_trend:{','.join(trending)}")
        risk_level = RISK_MEDIUM
        recommended_action = ACTION_MONITOR

    # Rule M2 — High Pain Early Postop (Days 1-5)
    if (
        ext.pain_severity is not None
        and ext.pain_severity >= 8
        and ext.postop_day <= 5
        and risk_level == RISK_ROUTINE
    ):
        triggered_rules.append("M2_high_pain_early_postop_monitor")
        risk_level = RISK_MEDIUM
        recommended_action = ACTION_MONITOR

    # Rule M3 — Fever Without Local Signs
    if ext.has_fever and not (ext.has_redness or ext.has_warmth or ext.has_drainage):
        if risk_level == RISK_ROUTINE:
            triggered_rules.append("M3_isolated_fever_monitor")
            risk_level = RISK_MEDIUM
            recommended_action = ACTION_MONITOR

    # Compute confidence
    confidence = _assess_confidence(ext, triggered_rules)

    return RuleEvaluation(
        risk_level=risk_level,
        triggered_rules=triggered_rules,
        recommended_action=recommended_action,
        escalation_needed=(risk_level != RISK_ROUTINE),
        confidence=confidence,
    )


def build_extraction_input(
    extraction_row: dict,
    patient_row: dict,
    recent_extractions: list[dict],
) -> ExtractionInput:
    
    import json
    from datetime import date

    surgery_date = patient_row["surgery_date"]
    if isinstance(surgery_date, str):
        surgery_date = date.fromisoformat(surgery_date)
    postop_day = (date.today() - surgery_date).days

    symptoms_raw = extraction_row.get("symptoms", "[]")
    symptoms = json.loads(symptoms_raw) if isinstance(symptoms_raw, str) else symptoms_raw

    missing_raw = extraction_row.get("missing_fields", "[]")
    missing = json.loads(missing_raw) if isinstance(missing_raw, str) else missing_raw

    details_raw = extraction_row.get("symptoms_details") or "{}"
    details = json.loads(details_raw) if isinstance(details_raw, str) else details_raw
    pain_severity = details.get("severity_score")
    if pain_severity is not None:
        try:
            pain_severity = int(pain_severity)
        except (ValueError, TypeError):
            pain_severity = None

    recent_symptom_history = []
    for row in recent_extractions:
        s_raw = row.get("symptoms", "[]")
        s = json.loads(s_raw) if isinstance(s_raw, str) else s_raw
        recent_symptom_history.append(s)

    return ExtractionInput(
        patient_id=str(extraction_row["patient_id"]),
        postop_day=postop_day,
        symptoms=symptoms,
        pain_severity=pain_severity,
        symptom_trend=details.get("trend"),
        symptom_location=details.get("location"),
        ambiguity_status=extraction_row.get("ambiguity_status", "clear"),
        missing_fields=missing,
        references_prior=bool(extraction_row.get("references_prior", False)),
        recent_symptom_history=recent_symptom_history,
    )