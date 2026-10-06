"""Unit tests for Planner and LLM response parsing.
"""

from core.planner import Planner


def test_standard_json_response():
    raw = """```json
{
  "thought": "Open Notepad",
  "action": "tool_call",
  "tool_name": "open_application",
  "parameters": {"app_name": "notepad"},
  "response": null
}
```"""
    parsed = Planner.parse_llm_response(raw)
    assert parsed["action"] == "tool_call"
    assert parsed["tool_name"] == "open_application"
    assert parsed["parameters"]["app_name"] == "notepad"


def test_json_with_trailing_commas():
    raw = """```json
{
  "thought": "Open Chrome with trailing commas",
  "action": "tool_call",
  "tool_name": "open_application",
  "parameters": {
    "app_name": "chrome",
  },
  "response": null,
}
```"""
    parsed = Planner.parse_llm_response(raw)
    assert parsed["action"] == "tool_call"
    assert parsed["tool_name"] == "open_application"
    assert parsed["parameters"]["app_name"] == "chrome"


def test_json_with_single_quotes():
    raw = """```json
{
  'thought': 'Open Chrome with single quotes',
  'action': 'tool_call',
  'tool_name': 'open_application',
  'parameters': {
    'app_name': 'chrome'
  },
  'response': null
}
```"""
    parsed = Planner.parse_llm_response(raw)
    assert parsed["action"] == "tool_call"
    assert parsed["tool_name"] == "open_application"
    assert parsed["parameters"]["app_name"] == "chrome"


def test_json_with_surrounding_conversational_text():
    raw = """Certainly! I am preparing to launch Google Chrome now.
```json
{
  "thought": "User wants to open Chrome",
  "action": "tool_call",
  "tool_name": "open_application",
  "parameters": {
    "app_name": "chrome"
  },
  "response": null
}
```
Please let me know if you need anything else!"""
    parsed = Planner.parse_llm_response(raw)
    assert parsed["action"] == "tool_call"
    assert parsed["tool_name"] == "open_application"
    assert parsed["parameters"]["app_name"] == "chrome"


def test_direct_action_name_as_action():
    raw = """```json
{
  "thought": "Launching brave browser directly",
  "action": "open_application",
  "parameters": {
    "app_name": "brave"
  }
}
```"""
    parsed = Planner.parse_llm_response(raw)
    assert parsed["action"] == "tool_call"
    assert parsed["tool_name"] == "open_application"
    assert parsed["parameters"]["app_name"] == "brave"


def test_malformed_json_with_regex_recovery():
    # Intentionally broken JSON missing braces or malformed
    raw = """I will run the tool now:
{ "tool_name": "open_application", "app_name": "calc", "action": "tool_call" """
    parsed = Planner.parse_llm_response(raw)
    assert parsed["action"] == "tool_call"
    assert parsed["tool_name"] == "open_application"
    assert parsed["parameters"]["app_name"] == "calc"
