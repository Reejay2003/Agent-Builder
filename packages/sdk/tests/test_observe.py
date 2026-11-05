import json
from pathlib import Path

import pytest

from agentbuilder.observe import INTERNAL_NAMES, TrajectoryError, from_dict, load, load_eval

FIX = Path(__file__).parent / "fixtures" / "atif"


def test_relay_tool_calling_run_is_read_completely():
    t = load(FIX / "relay_tool_calling.json")
    assert t.schema_version == "ATIF-v1.7" and t.model_name == "gpt-4.1-mini"
    assert len(t.llm_steps) == 2  # two model calls
    assert t.tools_used == ["demo__add_numbers", "demo__count_words"]
    add = next(c for c in t.tool_calls if c.name == "demo__add_numbers")
    assert add.arguments == {"a": 17.5, "b": 25} and add.result == "42.5" and add.status == "success"
    assert next(c for c in t.tool_calls if c.name == "demo__count_words").result == "3"
    assert t.final_text == "17.5 plus 25 is 42.5 and the text has 3 words."


def test_token_totals_come_from_the_trajectory_and_agree_with_the_steps():
    t = load(FIX / "relay_tool_calling.json")
    assert (t.prompt_tokens, t.completion_tokens) == (215, 27) and t.total_tokens == 242  # as reported by Relay
    assert sum(s.prompt_tokens or 0 for s in t.steps) == t.prompt_tokens  # and equal to the per-step sum


def test_relay_react_run():
    t = load(FIX / "relay_react.json")
    assert t.tools_used == ["demo__add_numbers"] and t.real_tool_calls[0].result == "42.5"
    assert t.final_text is not None and "42.5" in t.final_text and len(t.llm_steps) == 2


def test_nat_eval_output_filters_graph_internals():
    ((item_id, t),) = load_eval(FIX / "nat_native_eval.json").items()
    assert item_id and "demo_tools__add_numbers" in t.tools_used
    assert not (set(t.tools_used) & INTERNAL_NAMES)  # plumbing is not a tool
    assert any(c.name in INTERNAL_NAMES for c in t.tool_calls)  # but it is still available unfiltered
    assert t.prompt_tokens > 0


def test_nested_subagent_steps_are_flattened_in_order():
    step = lambda i, **kw: {"step_id": i, "source": "agent", "message": f"m{i}", **kw}  # noqa: E731
    raw = {
        "schema_version": "ATIF-v1.7",
        "steps": [step(1)],
        "subagent_trajectories": [{"steps": [step(2)], "subagent_trajectories": [{"steps": [step(3)]}]}],
    }
    assert [s.id for s in from_dict(raw).steps] == [1, 2, 3]


def test_tokens_fall_back_to_step_sums_when_no_totals_are_reported():
    raw = {
        "schema_version": "ATIF-v1.7",
        "steps": [
            {
                "step_id": 1,
                "source": "agent",
                "model_name": "m",
                "message": "a",
                "metrics": {"prompt_tokens": 10, "completion_tokens": 2},
            },
            {"step_id": 2, "source": "agent", "model_name": "m", "message": "b", "metrics": {"prompt_tokens": 20}},
        ],
    }
    t = from_dict(raw)
    assert (t.prompt_tokens, t.completion_tokens, t.total_tokens) == (30, 2, 32)


def test_tool_result_is_matched_by_call_id_not_by_position():
    raw = {
        "schema_version": "ATIF-v1.7",
        "steps": [
            {
                "step_id": 1,
                "source": "agent",
                "model_name": "m",
                "message": "",
                "tool_calls": [
                    {"tool_call_id": "A", "function_name": "a", "arguments": {}},
                    {"tool_call_id": "B", "function_name": "b", "arguments": {}},
                ],
                "observation": {
                    "results": [  # arrive in the opposite order
                        {"source_call_id": "B", "extra": {"tool_result": {"content": "from b", "status": "success"}}},
                        {"source_call_id": "A", "extra": {"tool_result": {"content": "from a", "status": "error"}}},
                    ]
                },
            }
        ],
    }
    calls = {c.name: c for c in from_dict(raw).tool_calls}
    assert (calls["a"].result, calls["a"].status) == ("from a", "error") and calls["b"].result == "from b"


def test_missing_optional_parts_do_not_crash():
    t = from_dict({"schema_version": "ATIF-v1.0", "steps": [{"step_id": 1, "source": "user"}]})
    assert t.final_text is None and t.tool_calls == () and t.total_tokens == 0 and t.llm_steps == ()


@pytest.mark.parametrize(
    "bad",
    [
        {},
        {"schema_version": "v2"},
        {"schema_version": "ATIF-v2.0", "steps": []},
        {"schema_version": "ATIF-v1.7"},
        {"schema_version": "ATIF-v1.7", "steps": "x"},
    ],
)
def test_non_atif_input_is_a_clear_error(bad):
    with pytest.raises(TrajectoryError):
        from_dict(bad)


def test_loading_errors_are_clear(tmp_path):
    with pytest.raises(TrajectoryError, match="cannot read"):
        load(tmp_path / "missing.json")
    (tmp_path / "bad.json").write_text("{not json")
    with pytest.raises(TrajectoryError, match="cannot read"):
        load(tmp_path / "bad.json")
    with pytest.raises(TrajectoryError, match="load_eval"):
        load(FIX / "nat_native_eval.json")  # a list is the other format
    (tmp_path / "single.json").write_text(json.dumps({"schema_version": "ATIF-v1.7", "steps": []}))
    with pytest.raises(TrajectoryError, match="item list"):
        load_eval(tmp_path / "single.json")


@pytest.mark.parametrize(
    "steps",
    [
        [{"step_id": 1, "source": "agent", "tool_calls": [{"function_name": "x", "arguments": '{"a": 1}'}]}],
        [{"step_id": "x", "source": "agent"}],
        ["not a step"],
    ],
)
def test_malformed_steps_give_a_trajectory_error_not_a_crash(steps):
    with pytest.raises(TrajectoryError, match=r"malformed trajectory \("):
        from_dict({"schema_version": "ATIF-v1.7", "steps": steps})


def _eval_file(tmp_path, items):
    f = tmp_path / "eval.json"
    f.write_text(json.dumps(items))
    return f


def test_eval_items_without_an_id_or_with_a_repeated_id_are_refused(tmp_path):
    t = {"schema_version": "ATIF-v1.7", "steps": []}
    with pytest.raises(TrajectoryError, match="item 1"):
        load_eval(_eval_file(tmp_path, [{"item_id": "a", "trajectory": t}, {"trajectory": t}]))
    with pytest.raises(TrajectoryError, match="twice"):
        load_eval(_eval_file(tmp_path, [{"item_id": "a", "trajectory": t}, {"item_id": "a", "trajectory": t}]))


def test_a_failed_eval_case_without_a_trajectory_maps_to_none_and_does_not_hide_the_others(tmp_path):
    t = {"schema_version": "ATIF-v1.7", "steps": []}
    got = load_eval(_eval_file(tmp_path, [{"item_id": "ok", "trajectory": t}, {"item_id": "failed"}]))
    assert got["failed"] is None and got["ok"] is not None
