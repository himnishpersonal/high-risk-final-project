"""
ACL Monitoring Agent — Streamlit Dashboard
"""

import datetime
import sys
from pathlib import Path

import streamlit as st
from sqlalchemy import desc
from sqlalchemy.orm import Session

_REPO_ROOT = str(Path(__file__).resolve().parents[1])
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from db.database import SessionLocal
from db.models import ClinicalExtraction, ConversationEvent, Patient, RuleEvaluation
from agent.workflow import run_acl_workflow

st.set_page_config(
    page_title="ACL Monitoring Agent",
    page_icon="🩺",
    layout="wide",
)

def get_db() -> Session:
    if "db" not in st.session_state:
        st.session_state.db = SessionLocal()
    return st.session_state.db


def compute_postop_day(surgery_date) -> int:
    if surgery_date is None:
        return 0
    if isinstance(surgery_date, str):
        surgery_date = datetime.date.fromisoformat(surgery_date)
    return max((datetime.date.today() - surgery_date).days, 0)


RISK_COLORS = {
    "routine":   "#4CAF50",
    "medium":    "#FFC107",
    "high":      "#FF9800",
    "emergency": "#F44336",
}

PHASE_COLORS = {
    "pre_op":  "#9C27B0",
    "post_op": "#4CAF50",
}


def risk_badge(level: str) -> str:
    color = RISK_COLORS.get(level, "#9E9E9E")
    return (
        f'<span style="background:{color};color:white;padding:2px 10px;'
        f'border-radius:10px;font-size:0.78em;font-weight:600;">{level.upper()}</span>'
    )


def phase_badge(phase: str) -> str:
    color = PHASE_COLORS.get(phase, "#9E9E9E")
    label = "PRE-OP" if phase == "pre_op" else "POST-OP"
    return (
        f'<span style="background:{color};color:white;padding:2px 10px;'
        f'border-radius:10px;font-size:0.78em;font-weight:600;">{label}</span>'
    )


def human_time(ts) -> str:
    if ts is None:
        return "—"
    if isinstance(ts, str):
        try:
            ts = datetime.datetime.fromisoformat(ts)
        except ValueError:
            return str(ts)
    now = datetime.datetime.utcnow()
    diff = now - ts
    seconds = int(diff.total_seconds())
    if seconds < 60:
        return "just now"
    if seconds < 3600:
        m = seconds // 60
        return f"{m} minute{'s' if m != 1 else ''} ago"
    if seconds < 86400:
        h = seconds // 3600
        return f"{h} hour{'s' if h != 1 else ''} ago"
    if seconds < 172800:
        return "yesterday"
    d = seconds // 86400
    return f"{d} days ago"


view = st.sidebar.radio(
    "View",
    ["SMS Simulator", "Clinician Dashboard", "Patient Timeline"],
)

if view == "SMS Simulator":
    st.title("SMS Simulator")

    db = get_db()

    patients = db.query(Patient).filter(Patient.status == "active").all()
    if not patients:
        st.warning("No active patients in the database. Run `python tests/seed_demo.py` first.")
        st.stop()

    sel_col, refresh_col = st.columns([5, 1])
    with sel_col:
        options = {f"{p.name}  ({p.phase})": p.patient_id for p in patients}
        selected_label = st.selectbox("Select patient", list(options.keys()))
        patient_id = options[selected_label]

    with refresh_col:
        st.write("")
        st.write("")
        if st.button("Refresh", use_container_width=True):
            st.session_state.pop("chat_patient_id", None)
            db.expire_all()
            st.rerun()

    patient = db.get(Patient, patient_id)
    postop_day = compute_postop_day(patient.surgery_date)

    open_escalations = (
        db.query(RuleEvaluation)
        .filter(
            RuleEvaluation.patient_id == patient_id,
            RuleEvaluation.escalation_needed == True,
        )
        .count()
    )
    if open_escalations:
        st.warning(
            f"⚠️  **{open_escalations} unresolved escalation{'s' if open_escalations != 1 else ''}** "
            f"for this patient — see Clinician Dashboard.",
            icon="🚨",
        )

    col1, col2, col3, col4, col5 = st.columns(5)
    col1.metric("Name", patient.name)
    with col2:
        st.write("Phase")
        st.markdown(phase_badge(patient.phase), unsafe_allow_html=True)
    col3.metric("Post-op day", postop_day)
    col4.metric("Graft type", patient.graft_type or "—")
    col5.metric("Protocol", patient.protocol_id or "—")

    st.divider()

    if (
        "chat_patient_id" not in st.session_state
        or st.session_state.chat_patient_id != patient_id
    ):
        st.session_state.chat_patient_id = patient_id
        st.session_state.messages = []

        events = (
            db.query(ConversationEvent)
            .filter(
                ConversationEvent.patient_id == patient_id,
                ConversationEvent.role.in_(["patient", "agent", "system"]),
            )
            .order_by(ConversationEvent.timestamp)
            .all()
        )

        for e in events:
            msg: dict = {"role": e.role, "text": e.message_text, "risk_level": None,
                         "extraction": None, "rule_result": None}

            if e.role == "patient":
                ext = (
                    db.query(ClinicalExtraction)
                    .filter(ClinicalExtraction.event_id == e.event_id)
                    .first()
                )
                if ext:
                    msg["extraction"] = {
                        "intent": ext.intent,
                        "symptoms": ext.symptoms or [],
                        "ambiguity_status": ext.ambiguity_status,
                        "references_prior": ext.references_prior,
                        "missing_fields": ext.missing_fields or [],
                    }
                    rule = (
                        db.query(RuleEvaluation)
                        .filter(RuleEvaluation.extraction_id == ext.extraction_id)
                        .first()
                    )
                    if rule:
                        msg["rule_result"] = {
                            "risk_level": rule.risk_level,
                            "triggered_rules": rule.triggered_rules or [],
                            "recommended_action": rule.recommended_action,
                            "confidence": rule.confidence,
                        }
                        msg["risk_level"] = rule.risk_level

            elif e.role == "agent":
                rule = (
                    db.query(RuleEvaluation)
                    .filter(RuleEvaluation.patient_id == patient_id)
                    .filter(RuleEvaluation.timestamp <= e.timestamp)
                    .order_by(desc(RuleEvaluation.timestamp))
                    .first()
                )
                if rule:
                    msg["risk_level"] = rule.risk_level
                    msg["rule_result"] = {
                        "risk_level": rule.risk_level,
                        "triggered_rules": rule.triggered_rules or [],
                        "recommended_action": rule.recommended_action,
                        "confidence": rule.confidence,
                    }

            st.session_state.messages.append(msg)

    for msg in st.session_state.messages:
        if msg["role"] == "patient":
            with st.chat_message("user"):
                st.write(msg["text"])
                if msg.get("extraction"):
                    ext = msg["extraction"]
                    with st.expander("Extraction details", expanded=False):
                        c1, c2 = st.columns(2)
                        c1.markdown(f"**Intent:** `{ext['intent']}`")
                        c2.markdown(
                            f"**Ambiguity:** `{ext['ambiguity_status']}`"
                        )
                        if ext["symptoms"]:
                            st.markdown(
                                "**Symptoms:** "
                                + " ".join(f"`{s}`" for s in ext["symptoms"])
                            )
                        else:
                            st.markdown("**Symptoms:** none")
                        st.markdown(
                            f"**References prior:** `{ext['references_prior']}`"
                        )
                        if ext["missing_fields"]:
                            st.markdown(
                                "**Missing fields:** "
                                + ", ".join(f"`{f}`" for f in ext["missing_fields"])
                            )

        elif msg["role"] == "system":
            with st.chat_message("assistant", avatar="🔔"):
                st.info(f"**Daily Check-in**\n\n{msg['text']}")

        else:
            with st.chat_message("assistant"):
                st.write(msg["text"])
                if msg.get("risk_level"):
                    st.markdown(risk_badge(msg["risk_level"]), unsafe_allow_html=True)
                if msg.get("rule_result"):
                    rr = msg["rule_result"]
                    with st.expander("Rule result", expanded=False):
                        c1, c2 = st.columns(2)
                        c1.markdown(
                            f"**Risk level:** {risk_badge(rr['risk_level'])}",
                            unsafe_allow_html=True,
                        )
                        c2.markdown(f"**Confidence:** `{rr['confidence']}`")
                        if rr["triggered_rules"]:
                            st.markdown(
                                "**Triggered rules:** "
                                + " ".join(f"`{r}`" for r in rr["triggered_rules"])
                            )
                        else:
                            st.markdown("**Triggered rules:** none")
                        st.markdown(
                            f"**Recommended action:** `{rr['recommended_action']}`"
                        )

    user_input = st.chat_input("Type a message as the patient...")

    if user_input:
        st.session_state.messages.append(
            {"role": "patient", "text": user_input, "risk_level": None,
             "extraction": None, "rule_result": None}
        )

        with st.spinner("Agent is thinking..."):
            final_state = run_acl_workflow(patient_id, user_input, db)

        response = final_state.get(
            "final_response",
            "We received your message. Your care team will follow up shortly.",
        )
        rule_result = final_state.get("rule_result") or {}
        extraction_result = final_state.get("extraction_result") or {}
        risk_level = rule_result.get("risk_level")

        if extraction_result:
            st.session_state.messages[-1]["extraction"] = {
                "intent": extraction_result.get("intent"),
                "symptoms": extraction_result.get("symptoms", []),
                "ambiguity_status": extraction_result.get("ambiguity_status"),
                "references_prior": extraction_result.get("references_prior", False),
                "missing_fields": extraction_result.get("missing_fields", []),
            }

        rr_dict = None
        if rule_result:
            rr_dict = {
                "risk_level": rule_result.get("risk_level"),
                "triggered_rules": rule_result.get("triggered_rules", []),
                "recommended_action": rule_result.get("recommended_action", ""),
                "confidence": rule_result.get("confidence", ""),
            }

        st.session_state.messages.append(
            {"role": "agent", "text": response, "risk_level": risk_level,
             "extraction": None, "rule_result": rr_dict}
        )

        st.rerun()


elif view == "Clinician Dashboard":
    st.title("Clinician Dashboard — Escalations")

    db = get_db()

    all_escalations = (
        db.query(RuleEvaluation)
        .filter(RuleEvaluation.escalation_needed == True)  # noqa: E712
        .order_by(desc(RuleEvaluation.timestamp))
        .all()
    )

    counts = {"emergency": 0, "high": 0, "medium": 0}
    for e in all_escalations:
        if e.risk_level in counts:
            counts[e.risk_level] += 1

    mc1, mc2, mc3, mc4 = st.columns(4)
    mc1.metric("Total escalations", len(all_escalations))
    mc2.metric("🔴 Emergency", counts["emergency"])
    mc3.metric("🟠 High", counts["high"])
    mc4.metric("🟡 Medium", counts["medium"])

    st.divider()

    if "esc_filter" not in st.session_state:
        st.session_state.esc_filter = "All"

    fcols = st.columns(4)
    for col, label in zip(fcols, ["All", "Emergency", "High", "Medium"]):
        if col.button(
            label,
            use_container_width=True,
            type="primary" if st.session_state.esc_filter == label else "secondary",
        ):
            st.session_state.esc_filter = label
            st.rerun()

    active_filter = st.session_state.esc_filter
    if active_filter == "All":
        filtered = all_escalations
    else:
        filtered = [e for e in all_escalations if e.risk_level == active_filter.lower()]

    st.write("")

    if not filtered:
        st.info(f"No {active_filter.lower()} escalations at this time.")
        st.stop()

    for ev in filtered:
        patient = db.get(Patient, ev.patient_id)
        patient_name = patient.name if patient else ev.patient_id
        postop_day = compute_postop_day(patient.surgery_date) if patient else "?"

        with st.container(border=True):
            header_cols = st.columns([3, 1, 1, 2, 1])
            header_cols[0].markdown(f"### {patient_name}")
            header_cols[1].markdown(f"**Day {postop_day}**")
            header_cols[2].markdown(
                risk_badge(ev.risk_level), unsafe_allow_html=True
            )
            header_cols[3].caption(human_time(ev.timestamp))

            with header_cols[4]:
                if st.button(
                    "Mark Resolved",
                    key=f"resolve_{ev.evaluation_id}",
                    type="secondary",
                    use_container_width=True,
                ):
                    ev.escalation_needed = False
                    db.commit()
                    st.success("Marked as resolved.")
                    st.rerun()

            detail_cols = st.columns([2, 3])
            with detail_cols[0]:
                triggered = ev.triggered_rules
                if isinstance(triggered, list) and triggered:
                    st.markdown(
                        "**Rules:** "
                        + " ".join(f"`{r}`" for r in triggered)
                    )
                else:
                    st.markdown("**Rules:** none")
                st.markdown(f"**Action:** `{ev.recommended_action}`")
                st.markdown(f"**Confidence:** `{ev.confidence}`")

            with detail_cols[1]:
                if ev.clinician_summary:
                    st.markdown("**Clinician summary:**")
                    st.info(ev.clinician_summary)
                else:
                    st.caption("No clinician summary available.")


elif view == "Patient Timeline":
    st.title("Patient Timeline")
    st.caption("Full recovery trajectory — all extractions and risk assessments chronologically.")

    db = get_db()

    patients = db.query(Patient).order_by(Patient.name).all()
    if not patients:
        st.warning("No patients in the database.")
        st.stop()

    options = {f"{p.name}  ({p.phase})": p.patient_id for p in patients}
    selected_label = st.selectbox("Select patient", list(options.keys()))
    patient_id = options[selected_label]
    patient = db.get(Patient, patient_id)

    postop_day = compute_postop_day(patient.surgery_date)
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Name", patient.name)
    with col2:
        st.write("Phase")
        st.markdown(phase_badge(patient.phase), unsafe_allow_html=True)
    col3.metric("Post-op day (today)", postop_day)
    col4.metric("Status", patient.status)

    st.divider()

    extractions = (
        db.query(ClinicalExtraction)
        .filter(ClinicalExtraction.patient_id == patient_id)
        .order_by(ClinicalExtraction.timestamp)
        .all()
    )

    if not extractions:
        st.info("No clinical extractions yet for this patient. Send some messages in the SMS Simulator.")
        st.stop()

    st.markdown(f"**{len(extractions)} extraction{'s' if len(extractions) != 1 else ''}** on record")
    st.write("")

    for i, ext in enumerate(extractions, 1):
        rule = (
            db.query(RuleEvaluation)
            .filter(RuleEvaluation.extraction_id == ext.extraction_id)
            .first()
        )

        is_escalated = rule and rule.escalation_needed
        risk_level = rule.risk_level if rule else None

        border_color = RISK_COLORS.get(risk_level, "#E0E0E0") if risk_level else "#E0E0E0"

        ts = ext.timestamp
        if ts:
            ts_str = (
                ts.strftime("%b %d, %Y  %H:%M")
                if hasattr(ts, "strftime")
                else str(ts)
            )
        else:
            ts_str = "—"

        with st.container(border=True):
            if is_escalated:
                st.error("⚠️ Escalation flagged for this entry")

            header = st.columns([2, 1, 1, 2])
            header[0].markdown(f"**Entry {i}** — {ts_str}")
            header[1].markdown(f"**Day {ext.postop_day or '?'}**")
            if risk_level:
                header[2].markdown(risk_badge(risk_level), unsafe_allow_html=True)
            header[3].markdown(f"`{ext.intent}`")

            symptom_cols = st.columns([3, 2])
            with symptom_cols[0]:
                if ext.symptoms:
                    st.markdown(
                        "**Symptoms:** "
                        + " ".join(f"`{s}`" for s in ext.symptoms)
                    )
                else:
                    st.markdown("**Symptoms:** none")
                st.markdown(f"**Ambiguity:** `{ext.ambiguity_status}`")
                st.markdown(f"**References prior:** `{ext.references_prior}`")

            with symptom_cols[1]:
                if rule:
                    if rule.triggered_rules:
                        st.markdown(
                            "**Triggered rules:** "
                            + " ".join(f"`{r}`" for r in rule.triggered_rules)
                        )
                    else:
                        st.markdown("**Triggered rules:** none")
                    st.markdown(f"**Action:** `{rule.recommended_action}`")
                else:
                    st.caption("No rule evaluation for this entry.")
