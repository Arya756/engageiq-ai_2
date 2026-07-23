from typing import Any, Dict, List, Optional, TypedDict

from langgraph.graph import END, StateGraph

from src.nudge.nudge_decision import NudgeDecision, NudgeDecisionEngine


# Define what data is stored in the graph state
class AgentState(TypedDict):
    current_state: str
    state_duration: int
    last_nudge_time: Optional[int]
    session_nudge_count: int
    # list of dicts: [{"type": "gentle_reminder", "success": True}, ...]
    effectiveness_history: List[Dict[str, Any]]
    decision: Optional[NudgeDecision]


# Initialize engine
engine = NudgeDecisionEngine(cooldown_seconds=300, max_nudges=5)


# Step Nodes
def evaluate_state(state: AgentState) -> AgentState:
    """Evaluates student's current activity level."""
    return state


def check_history(state: AgentState) -> AgentState:
    """Checks the history and limits."""
    return state


def decide_action(state: AgentState) -> AgentState:
    """Makes a decision based on history analysis."""
    decision = engine.should_nudge(
        current_state=state["current_state"],
        state_duration=state["state_duration"],
        last_nudge_time=state["last_nudge_time"],
        session_nudge_count=state["session_nudge_count"],
        effectiveness_history=state["effectiveness_history"],
    )
    state["decision"] = decision
    return state


# Setup Workflow
workflow = StateGraph(AgentState)
workflow.add_node("evaluate", evaluate_state)
workflow.add_node("check_history", check_history)
workflow.add_node("decide", decide_action)

workflow.add_edge("evaluate", "check_history")
workflow.add_edge("check_history", "decide")
workflow.add_edge("decide", END)

workflow.set_entry_point("evaluate")

# Compile Agent
nudge_agent = workflow.compile()
