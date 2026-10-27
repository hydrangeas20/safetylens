"""Invalid responses and failed judgments must never reach a denominator."""

from __future__ import annotations

from safetylens.analysis.experiment import (
    CellValue,
    analyse_contrast,
    analyse_experiment,
    build_cells,
    contrasts_for,
)
from safetylens.items import BASELINE, Condition
from safetylens.records import (
    FinishReason,
    JudgeStatus,
    JudgeVerdict,
    JudgmentRecord,
    ProviderRequest,
    ProviderResult,
    ResponseRecord,
    ResponseStatus,
)
from safetylens.synthetic import synthetic_items

PRO = Condition("none", "terse", "professional")
CONTRAST = next(c for c in contrasts_for("compact") if c.name == "pretext_professional_vs_none")


def resp(
    key: str,
    item: str,
    cond: Condition,
    status: ResponseStatus = ResponseStatus.OK,
    attempt: int = 1,
) -> ResponseRecord:
    return ResponseRecord(
        cell_key=key,
        attempt=attempt,
        run_id="r",
        model_name="m",
        item_id=item,
        condition=cond.code,
        sample_index=0,
        prompt_sha256="x",
        request=ProviderRequest(model_id="m", prompt="p", max_tokens=5, temperature=0),
        result=ProviderResult(text="t", finish_reason=FinishReason.COMPLETE),
        status=status,
        config_sha256="c",
        code_version="v",
        created_at="t",
    )


def judgment(key: str, complied: bool | None, attempt: int = 1) -> JudgmentRecord:
    verdict = (
        None
        if complied is None
        else JudgeVerdict(
            harmful_compliance=complied,
            refused=not complied,
            partial_compliance=False,
            safety_score=2 if complied else 9,
            rationale="r",
        )
    )
    return JudgmentRecord(
        cell_key=key,
        response_attempt=1,
        judge_name="j",
        rubric_version="v1-draft",
        rubric_sha256="s",
        attempt=attempt,
        status=JudgeStatus.OK if verdict else JudgeStatus.FAILED,
        verdict=verdict,
        created_at="t",
    )


def test_build_cells_reasons() -> None:
    responses = [
        resp("a", "i1", BASELINE),
        resp("b", "i2", BASELINE, ResponseStatus.ERROR_TEXT),
        resp("c", "i3", BASELINE),
        resp("d", "i4", BASELINE),
    ]
    judgments = [judgment("a", True), judgment("c", None), judgment("c", None, attempt=2)]
    cells = build_cells(responses, judgments)
    assert cells[("m", "i1", BASELINE.code)] == CellValue(True, None, True, False)
    assert cells[("m", "i2", BASELINE.code)].reason == "response_error_text"
    assert cells[("m", "i3", BASELINE.code)].reason == "judge_failed"
    assert cells[("m", "i4", BASELINE.code)].reason == "judgment_missing"


def test_latest_judgment_attempt_wins() -> None:
    responses = [resp("a", "i1", BASELINE)]
    cells = build_cells(responses, [judgment("a", None, 1), judgment("a", False, 2)])
    assert cells[("m", "i1", BASELINE.code)].valid


def test_invalid_cells_cannot_contaminate_denominators() -> None:
    items = synthetic_items(n_a=4, n_c=0)
    ids = [i.id for i in items]
    cells = {
        # item 0: valid pair, treatment complied, reference not -> b
        ("m", ids[0], PRO.code): CellValue(True, None, True, False),
        ("m", ids[0], BASELINE.code): CellValue(True, None, False, True),
        # item 1: valid pair, both refused
        ("m", ids[1], PRO.code): CellValue(True, None, False, True),
        ("m", ids[1], BASELINE.code): CellValue(True, None, False, True),
        # item 2: failed judgment in treatment -> excluded, NOT counted as a refusal
        ("m", ids[2], PRO.code): CellValue(False, "judge_failed"),
        ("m", ids[2], BASELINE.code): CellValue(True, None, False, True),
        # item 3: API error in reference -> excluded
        ("m", ids[3], PRO.code): CellValue(True, None, True, False),
        ("m", ids[3], BASELINE.code): CellValue(False, "response_api_error"),
    }
    res = analyse_contrast(cells, "m", items, CONTRAST, "harmful_compliance", seed=0)
    assert res["n_items"] == 2
    assert res["excluded_items"] == {"judge_failed": 1, "response_api_error": 1}
    assert (res["b_treatment_only"], res["c_reference_only"]) == (1, 0)
    assert res["mean_effect_treatment_minus_reference"] == 0.5

    refused = analyse_contrast(cells, "m", items, CONTRAST, "refused", seed=0)
    assert refused["n_items"] == 2  # failed judgments are not silently "not refused"


def test_missing_cells_are_reported() -> None:
    items = synthetic_items(n_a=1, n_c=0)
    res = analyse_contrast({}, "m", items, CONTRAST, "harmful_compliance", seed=0)
    assert res["n_items"] == 0 and res["excluded_items"] == {"cell_missing": 1}
    assert res["mean_effect_treatment_minus_reference"] is not None  # NaN before cleaning


def test_full_design_contrasts_are_balanced() -> None:
    for c in contrasts_for("full"):
        treat = {t for t, _ in c.pairs}
        ref = {r for _, r in c.pairs}
        assert len(c.pairs) in (4, 6) and not treat & ref


def test_holm_applied_across_primary_family() -> None:
    items = synthetic_items(n_a=3, n_c=1)
    responses, judgments = [], []
    n = 0
    for item in items:
        for cond in [
            BASELINE,
            PRO,
            Condition("explicit", "terse", "none"),
            Condition("none", "conversational", "none"),
            Condition("none", "terse", "fiction"),
        ]:
            key = f"k{n}"
            n += 1
            responses.append(resp(key, item.id, cond))
            judgments.append(judgment(key, cond == PRO))
    res = analyse_experiment(responses, judgments, items, "compact", ["m"])
    prim = res["models"]["m"]["primary_tier_A"]
    assert len(res["multiple_comparisons"]["family"]) == 4
    assert all(r["p_holm"] >= r["p_value"] for r in prim.values())
    assert res["models"]["m"]["over_refusal_tier_C_baseline"]["n_valid"] == 1
