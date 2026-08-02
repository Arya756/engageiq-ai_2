from unittest.mock import MagicMock, patch

from src.agents.intervention_agent import (
    InterventionSuggestion,
    build_prompt,
    generate_suggestions,
)


def test_build_prompt_empty_report():
    state = {
        "session_id": 1,
        "report": None,
        "prompt": "",
        "suggestions": [],
    }

    result = build_prompt(state)

    assert result["prompt"] == ""


def test_generate_suggestions_empty_prompt():
    state = {
        "session_id": 1,
        "report": None,
        "prompt": "",
        "suggestions": [],
    }

    result = generate_suggestions(state)

    assert result["suggestions"] == []


@patch("src.agents.intervention_agent.client.chat.completions.create")
def test_generate_suggestions(mock_create):
    response = MagicMock()
    response.choices = [MagicMock(message=MagicMock(content="""Category: Content
Minute: 14
Suggestion: Review concepts.

Category: Delivery
Minute: 15
Suggestion: Ask questions.

Category: Structure
Minute: 16
Suggestion: Add activity."""))]

    mock_create.return_value = response

    state = {
        "session_id": 1,
        "report": object(),
        "prompt": "dummy",
        "suggestions": [],
    }

    result = generate_suggestions(state)

    assert len(result["suggestions"]) == 3
    assert result["suggestions"][0].category == "Content"
    assert result["suggestions"][1].minute == 15
    assert result["suggestions"][2].suggestion == "Add activity."


@patch("src.agents.intervention_agent.client.chat.completions.create")
def test_invalid_response(mock_create):
    response = MagicMock()
    response.choices = [MagicMock(message=MagicMock(content="Hello"))]

    mock_create.return_value = response

    state = {
        "session_id": 1,
        "report": object(),
        "prompt": "dummy",
        "suggestions": [],
    }

    result = generate_suggestions(state)

    assert result["suggestions"] == []
