"""Typed NeMo Relay events for NAT's LangGraph agents (local addition, not in the upstream reference adapter).

Relay's LangChain callback handler only maps chain/graph runs, so the ATIF has no model or tool steps. NAT's ReAct and
tool-calling agents share BaseAgent._call_tool / _stream_llm / _call_llm; wrapping those emits real LLM and tool spans
(name, arguments, result, model, token usage) into the active Relay scope. Telemetry faults never affect the run."""
from __future__ import annotations

from typing import Any

_INSTALLED = False


def _safe(fn, *args, **kwargs):
    try:
        return fn(*args, **kwargs)
    except Exception:
        return None


def _jsonable(value: Any, limit: int = 2000) -> Any:
    if isinstance(value, dict):
        return {str(k): _jsonable(v, limit) for k, v in list(value.items())[:50]}
    if isinstance(value, (list, tuple)):
        return [_jsonable(v, limit) for v in list(value)[:50]]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value if not isinstance(value, str) else value[:limit]
    content = getattr(value, "content", None)
    if content is not None:
        return {"type": getattr(value, "type", type(value).__name__), "content": str(content)[:limit]}
    return str(value)[:limit]


def _model_name(agent: Any) -> str | None:
    llm = getattr(agent, "llm", None)
    return getattr(llm, "model_name", None) or getattr(llm, "model", None)


def install_typed_relay_events() -> None:
    global _INSTALLED
    if _INSTALLED:
        return
    import nemo_relay
    from nat.plugins.langchain.agent.base import BaseAgent

    orig_tool, orig_stream, orig_call = BaseAgent._call_tool, BaseAgent._stream_llm, BaseAgent._call_llm

    async def _call_tool(self, tool, tool_input, max_retries=3):
        args = tool_input if isinstance(tool_input, dict) else {"input": str(tool_input)}
        handle = _safe(nemo_relay.tools.call, tool.name, _jsonable(args))
        try:
            message = await orig_tool(self, tool, tool_input, max_retries)
        except BaseException as exc:
            if handle is not None:
                _safe(nemo_relay.tools.call_end, handle, nemo_relay.ToolExecutionResult({"error": f"{type(exc).__name__}: {exc}"}))
            raise
        if handle is not None:
            _safe(nemo_relay.tools.call_end, handle,
                  nemo_relay.ToolExecutionResult({"content": str(getattr(message, "content", ""))[:2000],
                                                  "status": getattr(message, "status", None)}))
        return message

    def _start(agent, inputs):
        model = _model_name(agent)
        request = _safe(nemo_relay.LLMRequest, {}, {"model": model, "input": _jsonable(inputs)})
        if request is None:
            return None, model
        return _safe(nemo_relay.llm.call, "nat-llm", request, model_name=model), model

    def _end(handle, model, message):
        if handle is None:
            return
        usage = getattr(message, "usage_metadata", None) or {}
        usage = {k: v for k, v in {"prompt_tokens": usage.get("input_tokens"), "completion_tokens": usage.get("output_tokens"),
                                   "total_tokens": usage.get("total_tokens")}.items() if v is not None}
        calls = [{"name": c.get("name"), "arguments": _jsonable(c.get("args"))} for c in (getattr(message, "tool_calls", None) or [])]
        annotated = _safe(nemo_relay.AnnotatedLLMResponse, model=model, message=str(getattr(message, "content", ""))[:2000],
                          usage=usage or None)  # tool calls are reported by the tool events; repeating them here duplicated them in the ATIF
        _safe(nemo_relay.llm.call_end, handle, {"content": str(getattr(message, "content", ""))[:2000]},
              annotated_response=annotated)

    async def _stream_llm(self, runnable, inputs, config=None):
        handle, model = _start(self, inputs)
        try:
            message = await orig_stream(self, runnable, inputs, config=config)
        except BaseException as exc:
            if handle is not None:
                _safe(nemo_relay.llm.call_end, handle, {"error": f"{type(exc).__name__}: {exc}"})
            raise
        _end(handle, model, message)
        return message

    async def _call_llm(self, llm, inputs):
        handle, model = _start(self, inputs)
        try:
            message = await orig_call(self, llm, inputs)
        except BaseException as exc:
            if handle is not None:
                _safe(nemo_relay.llm.call_end, handle, {"error": f"{type(exc).__name__}: {exc}"})
            raise
        _end(handle, model, message)
        return message

    BaseAgent._call_tool, BaseAgent._stream_llm, BaseAgent._call_llm = _call_tool, _stream_llm, _call_llm

    # The tool-calling agent has its own LLM call and runs tools through LangGraph's ToolNode.
    from nat.plugins.langchain.agent.tool_calling_agent.agent import ToolCallAgentGraph

    orig_invoke_llm, orig_tool_node = ToolCallAgentGraph._invoke_llm, ToolCallAgentGraph.tool_node

    async def _invoke_llm(self, state):
        handle, model = _start(self, {"messages": state.messages})
        try:
            message = await orig_invoke_llm(self, state)
        except BaseException as exc:
            if handle is not None:
                _safe(nemo_relay.llm.call_end, handle, {"error": f"{type(exc).__name__}: {exc}"})
            raise
        _end(handle, model, message)
        return message

    async def tool_node(self, state):
        requested = list(getattr(state.messages[-1], "tool_calls", None) or [])
        handles = {c.get("id"): _safe(nemo_relay.tools.call, c.get("name"), _jsonable(c.get("args") or {}),
                                      tool_call_id=c.get("id")) for c in requested}
        before = len(state.messages)
        try:
            result_state = await orig_tool_node(self, state)
        except BaseException as exc:
            for h in handles.values():
                if h is not None:
                    _safe(nemo_relay.tools.call_end, h, nemo_relay.ToolExecutionResult({"error": f"{type(exc).__name__}: {exc}"}))
            raise
        for m in result_state.messages[before:]:
            h = handles.get(getattr(m, "tool_call_id", None))
            if h is not None:
                _safe(nemo_relay.tools.call_end, h, nemo_relay.ToolExecutionResult(
                    {"content": str(getattr(m, "content", ""))[:2000], "status": getattr(m, "status", None)}))
        return result_state

    ToolCallAgentGraph._invoke_llm, ToolCallAgentGraph.tool_node = _invoke_llm, tool_node
    _INSTALLED = True
