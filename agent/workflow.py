"""
LangGraph workflow for ACL post-op monitoring.
"""

from functools import partial

import structlog
from langgraph.graph import END, StateGraph
from sqlalchemy.orm import Session

from agent.state import ACLWorkflowState

from agent.nodes.load_patient_context import load_patient_context
from agent.nodes.load_recent_history import load_recent_history
from agent.nodes.create_conversation_event import create_conversation_event
from agent.nodes.clinical_extraction import clinical_extraction
from agent.nodes.ambiguity_check import ambiguity_check
from agent.nodes.ask_followup import ask_followup
from agent.nodes.retrieve_knowledge import retrieve_knowledge
from agent.nodes.run_rules import run_rules
from agent.nodes.generate_response import generate_response
from agent.nodes.save_response import save_response
from agent.nodes.escalate_if_needed import escalate_if_needed

logger = structlog.get_logger()


def _build_graph() -> StateGraph:
    graph = StateGraph(ACLWorkflowState)

    graph.add_node("load_patient_context", load_patient_context)
    graph.add_node("load_recent_history", load_recent_history)
    graph.add_node("create_conversation_event", create_conversation_event)
    graph.add_node("clinical_extraction", clinical_extraction)
    graph.add_node("ask_followup", ask_followup)
    graph.add_node("retrieve_knowledge", retrieve_knowledge)
    graph.add_node("run_rules", run_rules)
    graph.add_node("generate_response", generate_response)
    graph.add_node("save_response", save_response)
    graph.add_node("escalate_if_needed", escalate_if_needed)

    graph.set_entry_point("load_patient_context")
    graph.add_edge("load_patient_context", "load_recent_history")
    graph.add_edge("load_recent_history", "create_conversation_event")
    graph.add_edge("create_conversation_event", "clinical_extraction")

    graph.add_conditional_edges(
        "clinical_extraction",
        ambiguity_check,
        {
            "ask_followup": "ask_followup",
            "retrieve_knowledge": "retrieve_knowledge",
        },
    )

    graph.add_edge("ask_followup", "save_response_followup")
    graph.add_node("save_response_followup", save_response)
    graph.add_edge("save_response_followup", END)

    graph.add_edge("retrieve_knowledge", "run_rules")
    graph.add_edge("run_rules", "generate_response")
    graph.add_edge("generate_response", "save_response")
    graph.add_edge("save_response", "escalate_if_needed")
    graph.add_edge("escalate_if_needed", END)

    return graph


def run_acl_workflow(patient_id: str, user_message: str, db: Session) -> dict:
    logger.info(
        "workflow_started",
        patient_id=patient_id,
        message_length=len(user_message),
    )

    graph = _build_graph()

    node_funcs = {
        "load_patient_context": load_patient_context,
        "load_recent_history": load_recent_history,
        "create_conversation_event": create_conversation_event,
        "clinical_extraction": clinical_extraction,
        "ask_followup": ask_followup,
        "retrieve_knowledge": retrieve_knowledge,
        "run_rules": run_rules,
        "generate_response": generate_response,
        "save_response": save_response,
        "save_response_followup": save_response,
        "escalate_if_needed": escalate_if_needed,
    }

    bound_graph = StateGraph(ACLWorkflowState)

    for name, fn in node_funcs.items():
        bound_graph.add_node(name, partial(fn, db=db))

    bound_graph.set_entry_point("load_patient_context")
    bound_graph.add_edge("load_patient_context", "load_recent_history")
    bound_graph.add_edge("load_recent_history", "create_conversation_event")
    bound_graph.add_edge("create_conversation_event", "clinical_extraction")

    bound_graph.add_conditional_edges(
        "clinical_extraction",
        ambiguity_check,
        {
            "ask_followup": "ask_followup",
            "retrieve_knowledge": "retrieve_knowledge",
        },
    )

    bound_graph.add_edge("ask_followup", "save_response_followup")
    bound_graph.add_edge("save_response_followup", END)

    bound_graph.add_edge("retrieve_knowledge", "run_rules")
    bound_graph.add_edge("run_rules", "generate_response")
    bound_graph.add_edge("generate_response", "save_response")
    bound_graph.add_edge("save_response", "escalate_if_needed")
    bound_graph.add_edge("escalate_if_needed", END)

    app = bound_graph.compile()

    initial_state: ACLWorkflowState = {
        "patient_id": patient_id,
        "user_message": user_message,
    }

    final_state = app.invoke(initial_state)

    logger.info(
        "workflow_completed",
        patient_id=patient_id,
        escalation_needed=final_state.get("escalation_needed", False),
        ambiguity_status=final_state.get("ambiguity_status"),
    )

    return final_state
