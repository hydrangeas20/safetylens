from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from safetylens.providers.base import LiveCallsDisabledError, require_live_opt_in
from safetylens.providers.fake import COMPLY_MARKER, FakeJudgeProvider, FakeModelProvider
from safetylens.providers.live import AnthropicProvider, GroqProvider
from safetylens.providers.replay import CassetteMissError, RecordingProvider, ReplayProvider
from safetylens.records import FinishReason, ProviderRequest

REQ = ProviderRequest(
    model_id="m",
    prompt="hello",
    max_tokens=50,
    temperature=0.0,
    seed=1,
    extra_params={"top_p": 0.9},
)


class TestLiveGuard:
    def test_config_flag_required(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("SAFETYLENS_ALLOW_LIVE", "1")
        with pytest.raises(LiveCallsDisabledError, match="allow_live"):
            require_live_opt_in(False)

    def test_env_required(self) -> None:
        with pytest.raises(LiveCallsDisabledError, match="SAFETYLENS_ALLOW_LIVE"):
            require_live_opt_in(True)

    def test_both_present(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("SAFETYLENS_ALLOW_LIVE", "1")
        require_live_opt_in(True)

    @pytest.mark.parametrize("cls", [GroqProvider, AnthropicProvider])
    def test_create_refuses_without_opt_in(self, cls: Any) -> None:
        with pytest.raises(LiveCallsDisabledError):
            cls.create(allow_live=True)


class StubGroq:
    def __init__(self, finish: str | None = "stop", raise_exc: bool = False) -> None:
        self.kwargs: dict[str, Any] = {}
        self.finish = finish
        self.raise_exc = raise_exc
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

    def _create(self, **kwargs: Any) -> Any:
        self.kwargs = kwargs
        if self.raise_exc:
            raise RuntimeError("400 property 'thinking' is unsupported")
        msg = SimpleNamespace(content="answer")
        return SimpleNamespace(
            choices=[SimpleNamespace(message=msg, finish_reason=self.finish)],
            usage=SimpleNamespace(prompt_tokens=3, completion_tokens=1),
            system_fingerprint="fp_1",
        )


class TestGroqAdapter:
    def test_maps_fields_and_passes_params(self) -> None:
        stub = StubGroq()
        res = GroqProvider(client=stub).generate(REQ)
        assert res.text == "answer" and res.finish_reason is FinishReason.COMPLETE
        assert res.model_fingerprint == "fp_1" and res.input_tokens == 3
        assert stub.kwargs["top_p"] == 0.9 and stub.kwargs["seed"] == 1

    def test_length_is_truncation(self) -> None:
        res = GroqProvider(client=StubGroq(finish="length")).generate(REQ)
        assert res.finish_reason is FinishReason.LENGTH and res.raw_finish_reason == "length"

    def test_exception_becomes_error_not_text(self) -> None:
        res = GroqProvider(client=StubGroq(raise_exc=True)).generate(REQ)
        assert res.text is None and res.error is not None and "thinking" in res.error

    def test_system_prompt(self) -> None:
        stub = StubGroq()
        GroqProvider(client=stub).generate(REQ.model_copy(update={"system": "rubric"}))
        assert stub.kwargs["messages"][0] == {"role": "system", "content": "rubric"}


class StubAnthropic:
    def __init__(self, stop: str = "end_turn", raise_exc: bool = False) -> None:
        self.kwargs: dict[str, Any] = {}
        self.stop = stop
        self.raise_exc = raise_exc
        self.messages = SimpleNamespace(create=self._create)

    def _create(self, **kwargs: Any) -> Any:
        self.kwargs = kwargs
        if self.raise_exc:
            raise RuntimeError("overloaded")
        return SimpleNamespace(
            content=[
                SimpleNamespace(type="text", text="a"),
                SimpleNamespace(type="other"),
                SimpleNamespace(type="text", text="b"),
            ],
            stop_reason=self.stop,
            model="judge-x",
            usage=SimpleNamespace(input_tokens=5, output_tokens=2),
        )


class TestAnthropicAdapter:
    def test_maps_fields(self) -> None:
        stub = StubAnthropic()
        res = AnthropicProvider(client=stub).generate(REQ.model_copy(update={"system": "s"}))
        assert res.text == "ab" and res.finish_reason is FinishReason.COMPLETE
        assert stub.kwargs["system"] == "s" and res.output_tokens == 2

    def test_max_tokens_is_truncation(self) -> None:
        res = AnthropicProvider(client=StubAnthropic(stop="max_tokens")).generate(REQ)
        assert res.finish_reason is FinishReason.LENGTH

    def test_exception(self) -> None:
        res = AnthropicProvider(client=StubAnthropic(raise_exc=True)).generate(REQ)
        assert res.error is not None and res.text is None


class TestReplay:
    def test_record_then_replay_including_repeats(self, tmp_path: Path) -> None:
        cassette = tmp_path / "c.jsonl"
        rec = RecordingProvider(FakeModelProvider("pretext_susceptible_noisy", seed=3), cassette)
        originals = [rec.generate(REQ) for _ in range(3)]  # identical requests, retries
        replay = ReplayProvider(cassette)
        assert [replay.generate(REQ) for _ in range(3)] == originals

    def test_miss_raises(self, tmp_path: Path) -> None:
        cassette = tmp_path / "c.jsonl"
        RecordingProvider(FakeModelProvider("null"), cassette).generate(REQ)
        replay = ReplayProvider(cassette)
        replay.generate(REQ)
        with pytest.raises(CassetteMissError):
            replay.generate(REQ)  # second occurrence was never recorded
        with pytest.raises(CassetteMissError):
            replay.generate(REQ.model_copy(update={"prompt": "different"}))

    def test_replay_is_not_live(self, tmp_path: Path) -> None:
        cassette = tmp_path / "c.jsonl"
        RecordingProvider(FakeModelProvider("null"), cassette).generate(REQ)
        assert ReplayProvider(cassette).is_live is False


class TestFakes:
    def test_fake_model_deterministic(self) -> None:
        a = FakeModelProvider("pretext_susceptible", seed=7)
        b = FakeModelProvider("pretext_susceptible", seed=7)
        assert a.generate(REQ) == b.generate(REQ)

    def test_fake_never_emits_real_content(self) -> None:
        p = FakeModelProvider("pretext_susceptible", seed=0)
        for i in range(30):
            text = p.generate(REQ.model_copy(update={"prompt": f"[pretext:x] q{i}"})).text or ""
            assert text.startswith("[SYNTHETIC-")

    def test_fake_judge_reads_marker(self) -> None:
        judge = FakeJudgeProvider()
        out = judge.generate(REQ.model_copy(update={"prompt": f"<response>\n{COMPLY_MARKER}"}))
        assert '"harmful_compliance": true' in (out.text or "")
