"""Resumable response collection with retries, truncation handling and provenance."""

from __future__ import annotations

import hashlib
from collections import defaultdict
from collections.abc import Callable, Mapping
from datetime import UTC, datetime
from importlib.metadata import PackageNotFoundError, version

from safetylens.config import ExperimentConfig
from safetylens.items import Item, design_conditions, prompt_sha256, render
from safetylens.providers.base import Provider, require_live_opt_in
from safetylens.quality import classify
from safetylens.records import ProviderRequest, ResponseRecord, ResponseStatus
from safetylens.storage import JsonlStore

# Statuses that will not change on retry with the same request.
_TERMINAL = {ResponseStatus.OK, ResponseStatus.PROVIDER_FILTER}


def code_version() -> str:
    try:
        return version("safetylens")
    except PackageNotFoundError:  # pragma: no cover
        return "unknown"


def utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def cell_key(config_sha: str, model: str, item_id: str, condition: str, sample: int) -> str:
    raw = f"{config_sha}|{model}|{item_id}|{condition}|{sample}"
    return hashlib.sha256(raw.encode()).hexdigest()


def collect(
    config: ExperimentConfig,
    items: list[Item],
    providers: Mapping[str, Provider],
    store: JsonlStore[ResponseRecord],
    *,
    run_id: str,
    clock: Callable[[], str] = utc_now,
) -> dict[str, int]:
    """Collect responses for every (model, item, condition, sample) cell.

    Cells whose latest attempt is terminal are skipped, so an interrupted run can
    be resumed by calling ``collect`` again with the same store.
    """
    if any(p.is_live for p in providers.values()):
        require_live_opt_in(config.allow_live)

    attempts: dict[str, list[ResponseRecord]] = defaultdict(list)
    for rec in store:
        attempts[rec.cell_key].append(rec)

    config_sha = config.sha256()
    s = config.sampling
    counts: dict[str, int] = defaultdict(int)
    for model in config.models:
        provider = providers[model.name]
        for item in items:
            for cond in design_conditions(config.design):
                prompt = render(item, cond)
                for sample in range(s.samples_per_cell):
                    key = cell_key(config_sha, model.name, item.id, cond.code, sample)
                    prior = sorted(attempts[key], key=lambda r: r.attempt)
                    if prior and prior[-1].status in _TERMINAL:
                        counts["skipped_complete"] += 1
                        continue
                    n = len(prior)
                    last_status = prior[-1].status if prior else None
                    while n < s.max_attempts:
                        n += 1
                        max_tokens = s.max_tokens
                        if last_status is ResponseStatus.TRUNCATED:
                            if s.truncation_retry_max_tokens is None:
                                break
                            max_tokens = s.truncation_retry_max_tokens
                        request = ProviderRequest(
                            model_id=model.model_id,
                            prompt=prompt,
                            max_tokens=max_tokens,
                            temperature=s.temperature,
                            seed=s.seed + sample,
                            extra_params=model.extra_params,
                        )
                        result = provider.generate(request)
                        status, detail = classify(
                            result, require_finish_reason=s.require_finish_reason
                        )
                        record = ResponseRecord(
                            cell_key=key,
                            attempt=n,
                            run_id=run_id,
                            model_name=model.name,
                            item_id=item.id,
                            condition=cond.code,
                            sample_index=sample,
                            prompt_sha256=prompt_sha256(prompt),
                            request=request,
                            result=result,
                            status=status,
                            status_detail=detail,
                            config_sha256=config_sha,
                            code_version=code_version(),
                            created_at=clock(),
                        )
                        store.append(record)
                        attempts[key].append(record)
                        last_status = status
                        if status in _TERMINAL:
                            break
                        if (
                            status is ResponseStatus.TRUNCATED
                            and max_tokens == s.truncation_retry_max_tokens
                        ):
                            break  # already retried at the larger budget
                    counts[f"final_{last_status}"] += 1
    return dict(counts)
