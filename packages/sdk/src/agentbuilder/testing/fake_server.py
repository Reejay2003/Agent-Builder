"""An OpenAI-compatible HTTP server backed by a FakeModel, so real agent frameworks run offline in tests.

    with FakeOpenAIServer(model) as server:
        run_agent(base_url=server.base_url, api_key="fake")     # e.g. NAT, Fabric, the OpenAI SDK

Supports `POST /v1/chat/completions` (streaming SSE and non-streaming) and `GET /v1/models`. Standard library only.
"""

from __future__ import annotations

import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from types import TracebackType
from typing import Any

from agentbuilder.testing.fake_model import FakeModel, ModelResponse, ScriptExhausted


def _tool_calls_json(resp: ModelResponse, *, with_index: bool) -> list[dict[str, Any]]:
    out = []
    for i, c in enumerate(resp.tool_calls):
        item: dict[str, Any] = {
            "id": c.id,
            "type": "function",
            "function": {"name": c.name, "arguments": json.dumps(dict(c.args))},
        }
        if with_index:
            item["index"] = i
        out.append(item)
    return out


def completion_body(resp: ModelResponse, model: str) -> dict[str, Any]:
    message: dict[str, Any] = {"role": "assistant", "content": resp.text or None}
    if resp.tool_calls:
        message["tool_calls"] = _tool_calls_json(resp, with_index=False)
    return {
        "id": "chatcmpl-fake",
        "object": "chat.completion",
        "created": int(time.time()),
        "model": model,
        "choices": [{"index": 0, "message": message, "finish_reason": resp.finish_reason}],
        "usage": {
            "prompt_tokens": resp.usage.prompt_tokens,
            "completion_tokens": resp.usage.completion_tokens,
            "total_tokens": resp.usage.total_tokens,
        },
    }


def stream_events(resp: ModelResponse, model: str, include_usage: bool) -> list[str]:
    base = {"id": "chatcmpl-fake", "object": "chat.completion.chunk", "created": int(time.time()), "model": model}

    def chunk(delta: dict[str, Any], finish: str | None = None) -> str:
        return (
            "data: " + json.dumps({**base, "choices": [{"index": 0, "delta": delta, "finish_reason": finish}]}) + "\n\n"
        )

    events = [chunk({"role": "assistant", "content": ""})]
    if resp.text:
        for i in range(0, len(resp.text), 24):  # several small chunks, like a real stream
            events.append(chunk({"content": resp.text[i : i + 24]}))
    if resp.tool_calls:
        events.append(chunk({"tool_calls": _tool_calls_json(resp, with_index=True)}))
    events.append(chunk({}, resp.finish_reason))
    if include_usage:
        usage = {
            "prompt_tokens": resp.usage.prompt_tokens,
            "completion_tokens": resp.usage.completion_tokens,
            "total_tokens": resp.usage.total_tokens,
        }
        events.append("data: " + json.dumps({**base, "choices": [], "usage": usage}) + "\n\n")
    events.append("data: [DONE]\n\n")
    return events


class FakeOpenAIServer:
    def __init__(self, model: FakeModel, host: str = "127.0.0.1", port: int = 0) -> None:
        self.model = model
        self._lock = threading.Lock()
        owner = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args: Any) -> None:  # keep test output quiet
                pass

            def _send_json(self, status: int, body: dict[str, Any]) -> None:
                data = json.dumps(body).encode()
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def do_GET(self) -> None:
                if self.path.rstrip("/").endswith("/models"):
                    self._send_json(200, {"object": "list", "data": [{"id": owner.model.name, "object": "model"}]})
                else:
                    self._send_json(404, {"error": {"message": "not found"}})

            def do_POST(self) -> None:
                if not self.path.rstrip("/").endswith("/chat/completions"):
                    self._send_json(404, {"error": {"message": "not found"}})
                    return
                payload = json.loads(self.rfile.read(int(self.headers.get("Content-Length", "0")) or 0) or b"{}")
                try:
                    with owner._lock:
                        resp = owner.model.respond(payload.get("messages", []), payload.get("tools", []))
                except ScriptExhausted as exc:
                    self._send_json(500, {"error": {"message": str(exc), "type": "fake_script_exhausted"}})
                    return
                name = str(payload.get("model") or owner.model.name)
                if payload.get("stream"):
                    include = bool((payload.get("stream_options") or {}).get("include_usage"))
                    self.send_response(200)
                    self.send_header("Content-Type", "text/event-stream")
                    self.send_header("Cache-Control", "no-cache")
                    self.end_headers()  # HTTP/1.0: the connection closes after the body, which ends the stream
                    for event in stream_events(resp, name, include):
                        self.wfile.write(event.encode())
                        self.wfile.flush()
                else:
                    self._send_json(200, completion_body(resp, name))

        self._server = ThreadingHTTPServer((host, port), Handler)
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)

    @property
    def base_url(self) -> str:
        host, port = self._server.server_address[:2]
        return f"http://{host!s}:{port}/v1"

    def start(self) -> FakeOpenAIServer:
        self._thread.start()
        return self

    def stop(self) -> None:
        self._server.shutdown()
        self._server.server_close()
        self._thread.join(timeout=5)

    def __enter__(self) -> FakeOpenAIServer:
        return self.start()

    def __exit__(
        self, exc_type: type[BaseException] | None, exc: BaseException | None, tb: TracebackType | None
    ) -> None:
        self.stop()
