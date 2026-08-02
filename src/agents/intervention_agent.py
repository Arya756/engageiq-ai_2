"""LLM-powered agent that suggests pedagogical interventions
based on engagement data.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, TypedDict

from groq import Groq
from langgraph.graph import END, StateGraph

from src.config.database import SessionLocal
from src.config.settings import settings
from src.reports.session_report import SessionReportData, SessionReportGenerator


@dataclass
class InterventionSuggestion:
    """Single teaching intervention."""

    category: str
    minute: int
    suggestion: str


class InterventionState(TypedDict):
    """LangGraph state."""

    session_id: int
    report: SessionReportData | None
    prompt: str
    suggestions: List[InterventionSuggestion]


client = Groq(api_key=settings.groq_api_key)


def load_report(state: InterventionState) -> InterventionState:
    """Load session report."""
    db = SessionLocal()
    try:
        generator = SessionReportGenerator(db)
        state["report"] = generator.generate(state["session_id"])
    finally:
        db.close()

    return state


def build_prompt(state: InterventionState) -> InterventionState:
    """Build prompt from report."""
    report = state["report"]

    if report is None or not report.has_data:
        state["prompt"] = ""
        return state

    timeline = "\n".join(
        f"Minute {minute}: {score * 100:.1f}%"
        for minute, score in sorted(report.timeline.items())
    )

    distraction = "\n".join(
        f"- Minute {d.minute}: {d.drop_pct * 100:.1f}% drop"
        for d in report.distraction_moments
    )

    valid_minutes = ", ".join(str(d.minute) for d in report.distraction_moments)

    state["prompt"] = f"""
You are an expert teaching coach.

Session Summary

Course: {report.course_name}
Average Engagement: {report.overall_average * 100:.1f}%
Engaged Students: {report.engaged_pct * 100:.1f}%

Timeline
{timeline}

Distraction Moments
{distraction}

Use ONLY these distraction minutes:
{valid_minutes}

Generate exactly 3 teaching intervention suggestions.

Rules:
- Use ONLY the information given.
- Never invent new minutes.
- Every suggestion must use one of these minutes: {valid_minutes}.
- Categorize each suggestion as Content, Delivery or Structure.
- Make every suggestion actionable for the teacher.
- Do not give generic advice.
- Keep each suggestion under 30 words.

Return exactly in this format:

Category: Content
Minute: <minute>
Suggestion: <text>

Category: Delivery
Minute: <minute>
Suggestion: <text>

Category: Structure
Minute: <minute>
Suggestion: <text>
"""

    return state


def generate_suggestions(state: InterventionState) -> InterventionState:
    """Generate intervention suggestions using Groq."""

    if not state["prompt"]:
        state["suggestions"] = []
        return state

    response = client.chat.completions.create(
        model=settings.groq_model,
        messages=[
            {
                "role": "system",
                "content": "You are an expert teaching coach.",
            },
            {
                "role": "user",
                "content": state["prompt"],
            },
        ],
        temperature=0.3,
    )

    text = response.choices[0].message.content or ""

    suggestions: list[InterventionSuggestion] = []

    blocks = text.strip().split("\n\n")

    for block in blocks:
        category = ""
        minute = 0
        suggestion = ""

        for line in block.splitlines():
            line = line.strip()

            if line.startswith("Category:"):
                category = line.replace("Category:", "").strip()

            elif line.startswith("1."):
                category = line.replace("1.", "").replace(":", "").strip()

            elif line.startswith("2."):
                category = line.replace("2.", "").replace(":", "").strip()

            elif line.startswith("3."):
                category = line.replace("3.", "").replace(":", "").strip()

            elif line.startswith("Minute:"):
                try:
                    minute = int(line.replace("Minute:", "").strip())
                except ValueError:
                    minute = 0
            elif line.startswith("Suggestion:"):
                suggestion = line.replace("Suggestion:", "").strip()

        if category and suggestion:
            suggestions.append(
                InterventionSuggestion(
                    category=category,
                    minute=minute,
                    suggestion=suggestion,
                )
            )

    state["suggestions"] = suggestions
    return state


workflow = StateGraph(InterventionState)

workflow.add_node("load_report", load_report)
workflow.add_node("build_prompt", build_prompt)
workflow.add_node("generate", generate_suggestions)

workflow.set_entry_point("load_report")

workflow.add_edge("load_report", "build_prompt")
workflow.add_edge("build_prompt", "generate")
workflow.add_edge("generate", END)

intervention_agent = workflow.compile()


class InterventionAgent:
    """LLM-powered intervention agent."""

    def generate(self, session_id: int) -> list[InterventionSuggestion]:
        state: InterventionState = {
            "session_id": session_id,
            "report": None,
            "prompt": "",
            "suggestions": [],
        }

        result = intervention_agent.invoke(state)
        return result["suggestions"]


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="Generate teaching intervention suggestions."
    )
    parser.add_argument("--session-id", type=int, required=True)

    args = parser.parse_args()

    agent = InterventionAgent()

    suggestions = agent.generate(args.session_id)

    if not suggestions:
        print("No suggestions generated.")
    else:
        for suggestion in suggestions:
            print(f"[{suggestion.category}] Minute {suggestion.minute}")
            print(f"  {suggestion.suggestion}")
            print()
