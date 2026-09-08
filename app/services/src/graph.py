import logging

from langgraph.graph import END, StateGraph, START
from langgraph.types import RetryPolicy

from app.services.src.state import MainGraphState
from app.services.src.nodes import Nodes

logger = logging.getLogger(__name__)

def build_graph():
    nodes = Nodes()
    graph = StateGraph(MainGraphState)

    graph.add_node("pre_processing_raw_emails",nodes.pre_processing_raw_emails)
    graph.add_node("regex_email_categorization",nodes.regex_email_categorization)
    graph.add_node("user_email_category_config",nodes.user_email_category_config)
    graph.add_node("llm_categorization",nodes.llm_categorization,retry_policy = RetryPolicy(max_attempts=3))
    graph.add_node("llm_supervisor",nodes.llm_supervisor,retry_policy = RetryPolicy(max_attempts=3))
    graph.add_node("retry_and_versioning",nodes.retry_and_versioning)

    graph.add_edge(START,"pre_processing_raw_emails")
    graph.add_edge("pre_processing_raw_emails","regex_email_categorization")
    graph.add_conditional_edges("regex_email_categorization",nodes.regex_router,{"regex_classified" : END , 
                                                                                "send_to_llm" :"llm_categorization" })
    graph.add_edge("llm_categorization","llm_supervisor")
    graph.add_conditional_edges("llm_supervisor",nodes.classification_router,{"Approved":END,"max_retry_reached":END,"reclassify":"retry_and_versioning"})
    graph.add_edge("retry_and_versioning","llm_categorization")

    builder = graph.compile()
    return builder

    
