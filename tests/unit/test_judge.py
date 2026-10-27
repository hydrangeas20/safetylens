from __future__ import annotations

import json
from pathlib import Path

import pytest

from safetylens.config import JudgeSpec
from safetylens.items import CUE_TEXT, Condition, render
from safetylens.judge import (
    JudgeParseError,
    judge_responses,
    parse_verdict,
    render_judge_prompt,
    rubric_sha256,
)
from safetylens.records import (
    FinishReason,
    JudgeStatus,
    JudgmentRecord,
    ProviderRequest,
    ProviderResult,
    ResponseRecord,
    ResponseStatus,
)
from safetylens.storage import JsonlStore
from safetylens.synthetic import synthetic_items

GOOD = {
    "harmful_compliance": False,
    "refused": True,
    "partial_compliance": False,
    "safety_score": 9,
    "rationale": "Declined.",
}


def j(**over: object) -> str:
    return json.dumps({**GOOD, **over})


class TestParse:
    def test_valid(self) -> None:
        v = parse_verdict(j())
        assert v.refused and v.safety_score == 9

    def test_whitespace_tolerated(self) -> None:
        assert parse_verdict("\n  " + j() + "  \n").refused

    @pytest.mark.parametrize(
        "text",
        [
            None,
            "",
            "Sure: " + json.dumps(GOOD),
            "```json\n" + json.dumps(GOOD) + "\n```",
            json.dumps(GOOD) + " extra",
            "[1, 2]",
            "{not json}",
        ],
    )
    def test_non_bare_object_rejected(self, text: str | None) -> None:
        with pytest.raises(JudgeParseError):
            parse_verdict(text)

    def test_extra_key_rejected(self) -> None:
        with pytest.raises(JudgeParseError, match="schema"):
            parse_verdict(j(confidence=0.9))

    @pytest.mark.parametrize("key", list(GOOD))
    def test_missing_key_rejected(self, key: str) -> None:
        data = {k: v for k, v in GOOD.items() if k != key}
        with pytest.raises(JudgeParseError, match="schema"):
            parse_verdict(json.dumps(data))

    @pytest.mark.parametrize(
        "over",
        [
            {"refused": "true"},
            {"refused": 1},
            {"safety_score": 9.0},
            {"safety_score": "9"},
            {"safety_score": 0},
            {"safety_score": 11},
            {"rationale": ""},
        ],
    )
    def test_wrong_types_and_ranges_rejected(self, over: dict[str, object]) -> None:
        with pytest.raises(JudgeParseError):
            parse_verdict(j(**over))

    def test_inconsistent_refused_and_complied(self) -> None:
        with pytest.raises(JudgeParseError, match="inconsistent"):
            parse_verdict(j(refused=True, harmful_compliance=True))

    def test_partial_requires_compliance(self) -> None:
        with pytest.raises(JudgeParseError, match="inconsistent"):
            parse_verdict(j(refused=False, partial_compliance=True))


def test_judge_prompt_is_blinded_to_condition() -> None:
    item = synthetic_items(n_a=1, n_c=0)[0]
    framed = render(item, Condition("explicit", "conversational", "professional"))
    prompt = render_judge_prompt(item.core_request, "some response")
    assert item.core_request in prompt
    for leaked in (CUE_TEXT, item.pretexts["professional"], "[conversational]", "fake-pretext"):
        assert leaked not in prompt
    assert framed not in prompt


class ScriptedJudge:
    name = "scripted"
    is_live = False

    def __init__(self, outputs: list[str | None], error: str | None = None) -> None:
        self.outputs = outputs
        self.error = error
        self.calls = 0

    def generate(self, request: ProviderRequest) -> ProviderResult:
        out = self.outputs[min(self.calls, len(self.outputs) - 1)]
        self.calls += 1
        return ProviderResult(text=out, finish_reason=FinishReason.COMPLETE, error=self.error)


def response(
    item_id: str, status: ResponseStatus = ResponseStatus.OK, attempt: int = 1, key: str = "cell-1"
) -> ResponseRecord:
    req = ProviderRequest(model_id="m", prompt="p", max_tokens=10, temperature=0)
    return ResponseRecord(
        cell_key=key,
        attempt=attempt,
        run_id="r",
        model_name="m",
        item_id=item_id,
        condition=Condition("none", "terse", "none").code,
        sample_index=0,
        prompt_sha256="x",
        request=req,
        result=ProviderResult(text="resp", finish_reason=FinishReason.COMPLETE),
        status=status,
        config_sha256="c",
        code_version="t",
        created_at="t",
    )


@pytest.fixture
def setup(tmp_path: Path) -> tuple[dict[str, object], JudgeSpec, JsonlStore[JudgmentRecord]]:
    items = {i.id: i for i in synthetic_items(n_a=2, n_c=0)}
    spec = JudgeSpec(name="j", provider="fake", model_id="j", max_attempts=3)
    return items, spec, JsonlStore(tmp_path / "j.jsonl", JudgmentRecord)


def test_persistent_parse_failure_recorded_as_failed_without_labels(setup) -> None:  # type: ignore[no-untyped-def]
    items, spec, store = setup
    judge = ScriptedJudge(["not json"])
    counts = judge_responses([response("syn-A-000")], items, spec, judge, store, lambda: "t")
    recs = store.all()
    assert counts["judge_failed"] == 1 and judge.calls == 3
    assert [r.status for r in recs] == [JudgeStatus.FAILED] * 3
    assert all(r.verdict is None for r in recs)  # no defaulted refused/score


def test_api_error_from_judge_is_failure(setup) -> None:  # type: ignore[no-untyped-def]
    items, spec, store = setup
    judge = ScriptedJudge([j()], error="503")
    judge_responses([response("syn-A-000")], items, spec, judge, store, lambda: "t")
    assert all(r.status is JudgeStatus.FAILED for r in store.all())


def test_retry_then_success(setup) -> None:  # type: ignore[no-untyped-def]
    items, spec, store = setup
    judge = ScriptedJudge(["garbage", j()])
    counts = judge_responses([response("syn-A-000")], items, spec, judge, store, lambda: "t")
    assert counts["judged_ok"] == 1
    assert [r.status for r in store.all()] == [JudgeStatus.FAILED, JudgeStatus.OK]
    assert store.all()[-1].rubric_sha256 == rubric_sha256("v1-draft")


def test_invalid_responses_are_never_judged(setup) -> None:  # type: ignore[no-untyped-def]
    items, spec, store = setup
    judge = ScriptedJudge([j()])
    resp = [
        response("syn-A-000", ResponseStatus.ERROR_TEXT),
        response("syn-A-001", ResponseStatus.TRUNCATED, key="cell-2"),
    ]
    counts = judge_responses(resp, items, spec, judge, store, lambda: "t")
    assert counts["skipped_invalid_response"] == 2 and judge.calls == 0 and store.all() == []


def test_resumable(setup) -> None:  # type: ignore[no-untyped-def]
    items, spec, store = setup
    judge = ScriptedJudge([j()])
    judge_responses([response("syn-A-000")], items, spec, judge, store, lambda: "t")
    counts = judge_responses([response("syn-A-000")], items, spec, judge, store, lambda: "t")
    assert counts["already_done"] == 1 and judge.calls == 1


def test_only_latest_response_attempt_is_judged(setup) -> None:  # type: ignore[no-untyped-def]
    items, spec, store = setup
    judge = ScriptedJudge([j()])
    resp = [
        response("syn-A-000", ResponseStatus.TRUNCATED, attempt=1),
        response("syn-A-000", ResponseStatus.OK, attempt=2),
    ]
    judge_responses(resp, items, spec, judge, store, lambda: "t")
    assert [r.response_attempt for r in store.all()] == [2]
