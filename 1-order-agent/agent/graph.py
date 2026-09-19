from langgraph.graph import StateGraph, START, END

from agent.state import AgentState, Input, Output
from agent.nodes.analyze import analyze_request
from agent.nodes.execute import execute_request
from agent.nodes.respond import generate_response


builder = StateGraph(AgentState, input_schema=Input, output_schema=Output)

builder.add_node("analyze", analyze_request)
builder.add_node("execute", execute_request)
builder.add_node("respond", generate_response)

builder.add_edge(START, "analyze")
builder.add_edge("analyze", "execute")
builder.add_edge("execute", "respond")
builder.add_edge("respond", END)

graph = builder.compile()
