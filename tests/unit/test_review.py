from __future__ import annotations

import csv
from pathlib import Path

import pytest

from safetylens.cli import main
from safetylens.review import CHECKS, load_reviews, review_status, template_header
from safetylens.synthetic import synthetic_items, write_items


def write_reviews(path: Path, rows: list[dict[str, str]]) -> Path:
    with path.open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=template_header())
        w.writeheader()
        for row in rows:
            w.writerow(row)
    return path


def row(item: str, reviewer: str, fail: str | None = None) -> dict[str, str]:
    r = {"item_id": item, "reviewer": reviewer, "date": "2026-10-27", "notes": ""}
    r.update({c: ("fail" if c == fail else "pass") for c in CHECKS})
    return r


@pytest.fixture
def items() -> list:  # type: ignore[type-arg]
    return synthetic_items(n_a=4, n_c=0)


def test_status_rules(tmp_path: Path, items) -> None:  # type: ignore[no-untyped-def]
    ids = [i.id for i in items]
    path = write_reviews(
        tmp_path / "r.csv",
        [
            row(ids[0], "alice"),
            row(ids[0], "bob"),
            row(ids[1], "alice"),
            row(ids[2], "alice"),
            row(ids[2], "bob", fail="R5_filler_neutral"),
        ],
    )
    status = review_status(items, load_reviews(path))
    assert status == {
        ids[0]: "approved",
        ids[1]: "needs_second_reviewer",
        ids[2]: "failed",
        ids[3]: "unreviewed",
    }


def test_same_reviewer_twice_is_not_two_reviews(tmp_path: Path, items) -> None:  # type: ignore[no-untyped-def]
    path = write_reviews(tmp_path / "r.csv", [row(items[0].id, "alice")] * 2)
    assert review_status(items, load_reviews(path))[items[0].id] == "needs_second_reviewer"


def test_later_row_supersedes_earlier_failure(tmp_path: Path, items) -> None:  # type: ignore[no-untyped-def]
    i = items[0].id
    path = write_reviews(
        tmp_path / "r.csv",
        [row(i, "alice", fail="R1_request_unchanged"), row(i, "alice"), row(i, "bob")],
    )
    assert review_status(items, load_reviews(path))[i] == "approved"


@pytest.mark.parametrize(
    ("mutate", "msg"),
    [
        (lambda r: r.update({"R1_request_unchanged": "maybe"}), "pass or fail"),
        (lambda r: r.update({"reviewer": " "}), "reviewer is required"),
    ],
)
def test_invalid_rows_rejected(tmp_path: Path, items, mutate, msg: str) -> None:  # type: ignore[no-untyped-def]
    r = row(items[0].id, "alice")
    mutate(r)
    path = write_reviews(tmp_path / "r.csv", [r])
    with pytest.raises(ValueError, match=msg):
        load_reviews(path)


def test_missing_columns_rejected(tmp_path: Path) -> None:
    p = tmp_path / "r.csv"
    p.write_text("item_id,reviewer,date\n")
    with pytest.raises(ValueError, match="missing columns"):
        load_reviews(p)


def test_unknown_item_rejected(tmp_path: Path, items) -> None:  # type: ignore[no-untyped-def]
    path = write_reviews(tmp_path / "r.csv", [row("nope", "alice")])
    with pytest.raises(ValueError, match="unknown items"):
        review_status(items, load_reviews(path))


def test_committed_template_matches_schema(repo_root: Path) -> None:
    with (repo_root / "docs/templates/item_review_template.csv").open() as fh:
        assert next(csv.reader(fh)) == template_header()


def test_cli_review_gate(tmp_path: Path, items) -> None:  # type: ignore[no-untyped-def]
    items_path = tmp_path / "items.jsonl"
    write_items(items, items_path)
    ids = [i.id for i in items]
    rows = [row(i, who) for i in ids for who in ("alice", "bob")]
    ok = write_reviews(tmp_path / "ok.csv", rows)
    partial = write_reviews(tmp_path / "partial.csv", rows[:-1])
    base = ["validate", "--items", str(items_path), "--require-approved", "--review"]
    assert main([*base, str(ok)]) == 0
    assert main([*base, str(partial)]) == 1
