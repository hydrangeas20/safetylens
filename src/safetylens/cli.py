"""Command-line interface. Every command works offline; live execution is refused."""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path

from safetylens.config import LIVE_PROVIDERS, load_config
from safetylens.items import design_conditions, load_items, render


def _cmd_historical(args: argparse.Namespace) -> int:
    from safetylens.historical.audit import build_from_archive, run_audit
    from safetylens.historical.manifest import load_manifest, verify_archive, verify_derived

    root = Path(args.repo)
    manifest_path = root / "historical" / "MANIFEST.json"
    if args.action == "build":
        derived = build_from_archive(Path(args.archive), root)
        print(f"wrote {len(derived)} derived files and historical/MANIFEST.json")
        return 0
    if args.action == "verify-archive":
        problems = verify_archive(Path(args.archive), load_manifest(manifest_path))
        print("\n".join(problems) or "archive matches manifest")
        return 1 if problems else 0
    if args.action == "verify":
        problems = verify_derived(root, load_manifest(manifest_path))
        print("\n".join(problems) or "derived files match manifest")
        return 1 if problems else 0
    # audit
    result = run_audit(root)
    mismatches = {k: v for k, v in result["comparison"].items() if v}
    print(result["flags"].to_string(index=False))
    print(
        "historical reproduction:",
        "MISMATCH " + json.dumps(mismatches) if mismatches else "matches original outputs",
    )
    print("excluded models:", json.dumps(result["exploratory"]["excluded_models"]))
    return 1 if mismatches else 0


def _cmd_validate(args: argparse.Namespace) -> int:
    if args.config:
        cfg = load_config(Path(args.config))
        print(
            f"config OK: {cfg.experiment} ({cfg.design}, {len(cfg.models)} models), "
            f"sha256={cfg.sha256()[:12]}"
        )
    if args.items:
        items = load_items(Path(args.items))
        tiers = {t: sum(i.tier == t for i in items) for t in "ABC"}
        print(f"items OK: {len(items)} items {tiers}")
    return 0


def _cmd_render(args: argparse.Namespace) -> int:
    items = load_items(Path(args.items))
    lines = [
        json.dumps({"item_id": item.id, "condition": cond.code, "prompt": render(item, cond)})
        for item in items
        for cond in design_conditions(args.design)
    ]
    text = "\n".join(lines) + "\n"
    if args.out == "-":
        sys.stdout.write(text)
    else:
        Path(args.out).write_text(text, encoding="utf-8")
    return 0


def _cmd_run(args: argparse.Namespace) -> int:
    """Run collection + judging with offline providers (fake or replay)."""
    from safetylens.analysis.experiment import analyse_experiment, render_report
    from safetylens.judge import judge_responses
    from safetylens.providers.base import Provider
    from safetylens.providers.fake import FakeJudgeProvider, FakeModelProvider
    from safetylens.providers.replay import ReplayProvider
    from safetylens.records import JudgmentRecord, ResponseRecord
    from safetylens.runner import collect, utc_now
    from safetylens.storage import JsonlStore

    cfg = load_config(Path(args.config))
    live = [m.name for m in cfg.models if m.provider in LIVE_PROVIDERS]
    if cfg.judge.provider in LIVE_PROVIDERS:
        live.append(cfg.judge.name)
    if live:
        print(
            "refusing to run: live providers configured "
            f"({', '.join(live)}). Live execution is not enabled in this version; it "
            "requires the preflight check and budget enforcement planned for the pilot "
            "phase and explicit approval.",
            file=sys.stderr,
        )
        return 2
    items = load_items(Path(cfg.items_path))
    out = Path(args.out)

    def provider_for(kind: str, profile: str | None, cassette: str | None) -> Provider:
        if kind == "fake":
            return FakeModelProvider(profile_name=profile or "null", seed=cfg.sampling.seed)
        if kind == "replay":
            if not cassette:
                raise SystemExit("replay provider requires --cassette")
            return ReplayProvider(Path(cassette))
        raise SystemExit(f"unsupported provider {kind}")

    models = {m.name: provider_for(m.provider, m.fake_profile, args.cassette) for m in cfg.models}
    judge: Provider = (
        FakeJudgeProvider()
        if cfg.judge.provider == "fake"
        else provider_for(cfg.judge.provider, None, args.judge_cassette)
    )
    responses: JsonlStore[ResponseRecord] = JsonlStore(out / "responses.jsonl", ResponseRecord)
    judgments: JsonlStore[JudgmentRecord] = JsonlStore(out / "judgments.jsonl", JudgmentRecord)
    print("collect:", collect(cfg, items, models, responses, run_id=args.run_id, clock=utc_now))
    print(
        "judge:",
        judge_responses(
            responses.all(), {i.id: i for i in items}, cfg.judge, judge, judgments, utc_now
        ),
    )
    res = analyse_experiment(
        responses.all(),
        judgments.all(),
        items,
        cfg.design,
        [m.name for m in cfg.models],
        seed=cfg.sampling.seed,
    )
    (out / "results.json").write_text(json.dumps(res, indent=2, sort_keys=True) + "\n")
    (out / "report.md").write_text(render_report(res, cfg.experiment))
    print(f"wrote {out / 'results.json'} and {out / 'report.md'}")
    return 0


def _cmd_synthetic(args: argparse.Namespace) -> int:
    from safetylens.synthetic import replay_synthetic, run_synthetic

    out = Path(args.out)
    first = run_synthetic(out / "recorded", design=args.design)
    second = replay_synthetic(out / "recorded", out / "replayed", design=args.design)
    first.pop("pipeline_counts")
    second.pop("pipeline_counts")
    identical = first == second
    print(json.dumps(first["integrity"], indent=2))
    print("replay reproduces recorded results exactly:", identical)
    print(f"report: {out / 'recorded' / 'report.md'}")
    return 0 if identical else 1


def _cmd_analyze(args: argparse.Namespace) -> int:
    from safetylens.analysis.experiment import analyse_experiment, render_report
    from safetylens.records import JudgmentRecord, ResponseRecord
    from safetylens.storage import JsonlStore

    items = load_items(Path(args.items))
    responses = JsonlStore(Path(args.responses), ResponseRecord).all()
    judgments = JsonlStore(Path(args.judgments), JudgmentRecord).all()
    models = sorted({r.model_name for r in responses})
    res = analyse_experiment(responses, judgments, items, args.design, models, seed=args.seed)
    Path(args.out).write_text(json.dumps(res, indent=2, sort_keys=True) + "\n")
    if args.report:
        Path(args.report).write_text(render_report(res, args.title))
    print(f"wrote {args.out}")
    return 0


def _cmd_report(args: argparse.Namespace) -> int:
    from safetylens.analysis.experiment import render_report

    res = json.loads(Path(args.results).read_text())
    Path(args.out).write_text(render_report(res, args.title))
    return 0


def _cmd_design(args: argparse.Namespace) -> int:
    from safetylens.design import comparison_report

    text = comparison_report(n_models=args.models, reps=args.reps)
    if args.out == "-":
        print(text)
    else:
        Path(args.out).write_text(text)
    return 0


def _cmd_scan(args: argparse.Namespace) -> int:
    from safetylens.scan import scan_repo

    findings = scan_repo(Path(args.root))
    for f in findings:
        print(f"{f.path}: {f.kind} ({f.detail})")
    print(f"{len(findings)} finding(s)")
    return 1 if findings else 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="safetylens", description=__doc__)
    sub = p.add_subparsers(dest="command", required=True)

    h = sub.add_parser("historical", help="audit the archived 2026 experiment")
    h.add_argument("action", choices=["build", "verify-archive", "verify", "audit"])
    h.add_argument("--archive", help="local checkout of safetylens-research (build/verify)")
    h.add_argument("--repo", default=".")
    h.set_defaults(func=_cmd_historical)

    v = sub.add_parser("validate", help="validate a config and/or items file")
    v.add_argument("--config")
    v.add_argument("--items")
    v.set_defaults(func=_cmd_validate)

    r = sub.add_parser("render", help="render prompts for every item x condition")
    r.add_argument("--items", required=True)
    r.add_argument("--design", choices=["full", "compact"], default="full")
    r.add_argument("--out", default="-")
    r.set_defaults(func=_cmd_render)

    run = sub.add_parser("run", help="collect + judge + analyse with offline providers")
    run.add_argument("--config", required=True)
    run.add_argument("--out", required=True)
    run.add_argument("--run-id", default="local")
    run.add_argument("--cassette")
    run.add_argument("--judge-cassette")
    run.set_defaults(func=_cmd_run)

    s = sub.add_parser("synthetic", help="offline end-to-end experiment + strict replay check")
    s.add_argument("--out", default=tempfile.gettempdir() + "/safetylens-synthetic")
    s.add_argument("--design", choices=["full", "compact"], default="full")
    s.set_defaults(func=_cmd_synthetic)

    a = sub.add_parser("analyze", help="analyse stored responses and judgments")
    a.add_argument("--responses", required=True)
    a.add_argument("--judgments", required=True)
    a.add_argument("--items", required=True)
    a.add_argument("--design", choices=["full", "compact"], required=True)
    a.add_argument("--out", required=True)
    a.add_argument("--report")
    a.add_argument("--title", default="SafetyLens analysis")
    a.add_argument("--seed", type=int, default=0)
    a.set_defaults(func=_cmd_analyze)

    rp = sub.add_parser("report", help="render a markdown report from results.json")
    rp.add_argument("--results", required=True)
    rp.add_argument("--out", required=True)
    rp.add_argument("--title", default="SafetyLens analysis")
    rp.set_defaults(func=_cmd_report)

    d = sub.add_parser("design", help="power/cost comparison of compact vs full designs")
    d.add_argument("action", choices=["compare"])
    d.add_argument("--models", type=int, default=3)
    d.add_argument("--reps", type=int, default=2000)
    d.add_argument("--out", default="-")
    d.set_defaults(func=_cmd_design)

    sc = sub.add_parser("scan", help="scan tracked files for secrets and unredacted output")
    sc.add_argument("--root", default=".")
    sc.set_defaults(func=_cmd_scan)
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    code: int = args.func(args)
    return code


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
