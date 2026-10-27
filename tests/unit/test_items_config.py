from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from safetylens.config import ExperimentConfig, load_config
from safetylens.items import (
    BASELINE,
    CUE_TEXT,
    Condition,
    Item,
    compact_design,
    design_conditions,
    full_design,
    load_items,
    render,
)
from safetylens.synthetic import synthetic_items


def base_item(**over: object) -> dict[str, object]:
    data: dict[str, object] = {
        "id": "x1",
        "tier": "A",
        "category": "c",
        "source": "authored",
        "core_request": "CORE",
        "terse": "CORE",
        "conversational": "hello CORE",
        "pretexts": {
            "filler": "It is sunny.",
            "fiction": "A short story.",
            "professional": "For my job.",
        },
        "compliance_appropriate": "never",
    }
    data.update(over)
    return data


class TestDesign:
    def test_full_has_sixteen_unique_conditions(self) -> None:
        conds = full_design()  # 2 cues x 2 registers x 4 pretext levels (incl. filler)
        assert len(conds) == 16 == len(set(conds))

    def test_compact_is_subset_of_full_and_includes_baseline(self) -> None:
        assert set(compact_design()) <= set(full_design())
        assert BASELINE in compact_design() and len(compact_design()) == 6
        assert Condition("none", "terse", "filler") in compact_design()

    def test_condition_code_roundtrip(self) -> None:
        for c in full_design():
            assert Condition.parse(c.code) == c

    def test_bad_condition_code(self) -> None:
        with pytest.raises(ValueError, match="invalid condition"):
            Condition.parse("cue=maybe|reg=terse|pre=none")

    def test_unknown_design(self) -> None:
        with pytest.raises(ValueError, match="unknown design"):
            design_conditions("tiny")


class TestRender:
    def test_core_request_constant_across_all_conditions(self) -> None:
        item = synthetic_items(n_a=1, n_c=0)[0]
        prompts = [render(item, c) for c in full_design()]
        assert all(item.core_request in p for p in prompts)
        assert len(set(prompts)) == 16

    def test_cue_only_when_explicit(self) -> None:
        item = synthetic_items(n_a=1, n_c=0)[0]
        for c in full_design():
            assert (CUE_TEXT in render(item, c)) == (c.cue == "explicit")

    def test_pretext_only_when_requested(self) -> None:
        item = synthetic_items(n_a=1, n_c=0)[0]
        for c in full_design():
            p = render(item, c)
            assert (item.pretexts["fiction"] in p) == (c.pretext == "fiction")
            assert (item.pretexts["professional"] in p) == (c.pretext == "professional")
            assert (item.pretexts["filler"] in p) == (c.pretext == "filler")

    def test_override_used(self) -> None:
        code = BASELINE.code
        item = Item.model_validate(base_item(overrides={code: "Please: CORE"}))
        assert render(item, BASELINE) == "Please: CORE"


class TestItemValidation:
    def test_valid(self) -> None:
        Item.model_validate(base_item())

    @pytest.mark.parametrize(
        ("over", "msg"),
        [
            ({"terse": "something else"}, "verbatim"),
            ({"conversational": "nope"}, "verbatim"),
            ({"tier": "C"}, "requires always"),
            ({"overrides": {BASELINE.code: "drops the request"}}, "override"),
            ({"overrides": {"cue=x|reg=terse|pre=none": "CORE"}}, "invalid condition"),
            ({"pretexts": {"fiction": "story.", "professional": "job."}}, "filler"),
            (
                {
                    "pretexts": {
                        "filler": "The weather is mild and the sky is clear and calm today.",
                        "fiction": "A story.",
                        "professional": "My job.",
                    }
                },
                "length-matched",
            ),
            (
                {
                    "pretexts": {
                        "filler": "It is sunny.",
                        "fiction": "CORE in a story.",
                        "professional": "For my job.",
                    }
                },
                "must not restate",
            ),
            ({"id": "bad id!"}, "pattern"),
            ({"unexpected": 1}, "Extra inputs"),
        ],
    )
    def test_invalid(self, over: dict[str, object], msg: str) -> None:
        with pytest.raises(ValidationError, match=msg):
            Item.model_validate(base_item(**over))

    def test_duplicate_ids_rejected(self, tmp_path: Path) -> None:
        p = tmp_path / "items.jsonl"
        line = Item.model_validate(base_item()).model_dump_json()
        p.write_text(line + "\n" + line + "\n")
        with pytest.raises(ValueError, match="duplicate item id"):
            load_items(p)

    def test_empty_file_rejected(self, tmp_path: Path) -> None:
        p = tmp_path / "items.jsonl"
        p.write_text("\n")
        with pytest.raises(ValueError, match="no items"):
            load_items(p)


def cfg(**over: object) -> dict[str, object]:
    data: dict[str, object] = {
        "experiment": "t",
        "items_path": "i.jsonl",
        "design": "full",
        "models": [{"name": "a", "provider": "fake", "model_id": "a"}],
        "judge": {"name": "j", "provider": "fake", "model_id": "j"},
    }
    data.update(over)
    return data


class TestConfig:
    def test_defaults_are_safe(self) -> None:
        c = ExperimentConfig.model_validate(cfg())
        assert c.allow_live is False and c.sampling.require_finish_reason is True
        assert not c.uses_live_providers()

    def test_duplicate_model_names(self) -> None:
        m = {"name": "a", "provider": "fake", "model_id": "a"}
        with pytest.raises(ValidationError, match="unique"):
            ExperimentConfig.model_validate(cfg(models=[m, m]))

    def test_live_with_allow_requires_budget(self) -> None:
        m = [{"name": "a", "provider": "groq", "model_id": "x"}]
        with pytest.raises(ValidationError, match="budget"):
            ExperimentConfig.model_validate(cfg(models=m, allow_live=True))
        ok = ExperimentConfig.model_validate(cfg(models=m, allow_live=True, budget_usd_cap=5))
        assert ok.uses_live_providers()

    def test_extra_fields_forbidden(self) -> None:
        with pytest.raises(ValidationError):
            ExperimentConfig.model_validate(cfg(surprise=True))

    def test_sha_stable_and_sensitive(self) -> None:
        a = ExperimentConfig.model_validate(cfg())
        b = ExperimentConfig.model_validate(cfg())
        c = ExperimentConfig.model_validate(cfg(design="compact"))
        assert a.sha256() == b.sha256() != c.sha256()

    @pytest.mark.parametrize("name", ["synthetic.yaml", "experiment_v1_draft.yaml"])
    def test_committed_configs_validate(self, repo_root: Path, name: str) -> None:
        c = load_config(repo_root / "configs" / name)
        assert c.allow_live is False
