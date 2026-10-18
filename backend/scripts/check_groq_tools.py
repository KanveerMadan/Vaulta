"""
Checks that the configured Groq model (GROQ_MODEL, default in app/core/config.py) does the tool calling the chat
agent needs: given Vaulta's own tool schemas and a question, it asks for a known tool with valid JSON arguments, and
after a (made-up) tool result it answers in plain text. Run it before changing GROQ_MODEL, and when Groq retires a
model. Two small requests; no user data; the key is read from the environment or backend/.env and never printed.

    cd backend && venv/bin/python -m scripts.check_groq_tools
"""

from __future__ import annotations

import json
import sys

from app.core.config import settings
from app.services import llm
from app.services.chat import SYSTEM_PROMPT
from app.services.chat_tools import TOOL_SCHEMAS

QUESTION = "How much did I spend on food last month?"
FAKE_RESULT = {"total": "4210.50", "transactions": 23, "period": "last month", "category": "Food & Dining"}


def main() -> int:
    names = {t["function"]["name"] for t in TOOL_SCHEMAS}
    messages = [{"role": "system", "content": SYSTEM_PROMPT.format(today="Saturday 18 October 2026")},
                {"role": "user", "content": QUESTION}]
    first = llm.complete(messages, TOOL_SCHEMAS)
    calls = first.get("tool_calls") or []
    if not calls:
        print(f"FAIL {settings.GROQ_MODEL}: no tool call for a question that needs one")
        return 1
    for call in calls:
        name = call["function"]["name"]
        args = json.loads(call["function"].get("arguments") or "{}")        # raises if the arguments aren't JSON
        if name not in names or not isinstance(args, dict):
            print(f"FAIL {settings.GROQ_MODEL}: called {name!r}, not one of Vaulta's tools")
            return 1
    messages.append({"role": "assistant", "content": first.get("content") or "", "tool_calls": calls})
    messages += [{"role": "tool", "tool_call_id": c["id"], "content": json.dumps(FAKE_RESULT)} for c in calls]
    second = llm.complete(messages, TOOL_SCHEMAS)
    if second.get("tool_calls") or not (second.get("content") or "").strip():
        print(f"FAIL {settings.GROQ_MODEL}: no plain answer after the tool result")
        return 1
    print(f"OK {settings.GROQ_MODEL}: called {sorted({c['function']['name'] for c in calls})}, then answered in text")
    return 0


if __name__ == "__main__":
    sys.exit(main())
