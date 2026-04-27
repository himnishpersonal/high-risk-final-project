"""
Node: retrieve_knowledge

Queries the protocol knowledge base (ChromaDB / RAG) for relevant clinical information.
"""

from typing import Optional

from agent.state import ACLWorkflowState
from rag.retriever import retrieve


def infer_topic_from_rules(triggered_rules: list[str]) -> Optional[str]:

    if not triggered_rules:
        return None
    
    rules_str = " ".join(triggered_rules).lower()
    
    if "dvt" in rules_str or "calf" in rules_str:
        return "dvt"
    elif "ssi" in rules_str or "infection" in rules_str:
        return "infection"
    elif "pain" in rules_str:
        return "pain"
    
    return None


def retrieve_knowledge(state: ACLWorkflowState, *, db) -> dict:

    patient_context = state.get("patient_context")
    user_message = state.get("user_message", "")
    extraction_result = state.get("extraction_result")
    rule_result = state.get("rule_result")
    
    if not patient_context:
        return {"retrieved_knowledge": []}
    
    phase = patient_context.get("phase", "post_op")
    
    query_parts = [user_message]
    
    if extraction_result and extraction_result.get("symptoms"):
        symptoms = extraction_result["symptoms"]
        query_parts.append(" ".join(symptoms))
    
    query_text = " ".join(query_parts).strip()
    
    if not query_text:
        return {"retrieved_knowledge": []}

    topic = None
    if rule_result and rule_result.get("triggered_rules"):
        topic = infer_topic_from_rules(rule_result["triggered_rules"])
    
    chunks = retrieve(query_text=query_text, phase=phase, topic=topic)
    
    return {"retrieved_knowledge": chunks}
