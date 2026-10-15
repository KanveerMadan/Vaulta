"""
A stand-in for the Groq chat-completions API (OpenAI format) for browser
tests. Deterministic: questions about budgets propose set_budget (an action
the user must confirm); anything else calls spend_summary for this month,
and once tool results come back it answers in one line.
"""

import json
import re
from datetime import date
from http.server import BaseHTTPRequestHandler, HTTPServer


def answer(messages: list) -> dict:
    last = messages[-1]
    if last["role"] == "tool":
        if "awaiting_user_confirmation" in last["content"]:
            return {"role": "assistant", "content": "I've prepared that change. Confirm it below."}
        return {"role": "assistant", "content": "Here's your spending this month, from your own transactions."}
    question = last["content"].lower()
    if "budget" in question and (m := re.search(r"(\d[\d,]*)", question)):
        call = ("set_budget", {"category": "Food & Dining", "amount": int(m[1].replace(",", ""))})
    else:
        today = date.today()
        call = ("spend_summary", {"start": today.replace(day=1).isoformat(), "end": today.isoformat()})
    return {"role": "assistant", "content": "", "tool_calls": [
        {"id": "call_1", "type": "function", "function": {"name": call[0], "arguments": json.dumps(call[1])}}]}


class Handler(BaseHTTPRequestHandler):
    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        out = json.dumps({"choices": [{"message": answer(body["messages"])}]}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(out)))
        self.end_headers()
        self.wfile.write(out)

    def do_GET(self):   # readiness probe
        self.send_response(200)
        self.end_headers()

    def log_message(self, *args):
        pass


if __name__ == "__main__":
    HTTPServer(("127.0.0.1", 8002), Handler).serve_forever()
