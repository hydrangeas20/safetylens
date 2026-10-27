"""Documentation integrity: local links, images, and Mermaid diagram safety.

The README once failed to render on GitHub because a Mermaid label contained
``safetylens-research@b5d0dba``: Mermaid 11 parses ``name@`` as an edge ID
(LINK_ID token). Full parsing is done by the Mermaid CLI in CI; these tests are
the fast offline guard.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
DOCS = sorted(
    [ROOT / "README.md", *(ROOT / "docs").glob("*.md"), *(ROOT / "historical").glob("*.md")]
)
LINK = re.compile(r"(?<!\!)\[[^\]]*\]\(([^)\s]+)\)")
IMAGE = re.compile(r"!\[[^\]]*\]\(([^)\s]+)\)|<img[^>]+src=\"([^\"]+)\"")
MERMAID = re.compile(r"```mermaid\n(.*?)```", re.DOTALL)
FENCED = re.compile(r"^```.*?^```", re.DOTALL | re.MULTILINE)
INLINE_CODE = re.compile(r"`[^`\n]+`")


def _strip_code(text: str) -> str:
    """Links quoted inside code are examples, not references."""
    return INLINE_CODE.sub("", FENCED.sub("", text))


def _local_targets(text: str, pattern: re.Pattern[str]) -> list[str]:
    out = []
    for m in pattern.finditer(text):
        target = next(g for g in m.groups() if g)
        if target.startswith(("http://", "https://", "mailto:", "#")):
            continue
        out.append(target.split("#", 1)[0])
    return out


@pytest.mark.parametrize("doc", DOCS, ids=lambda p: p.relative_to(ROOT).as_posix())
def test_local_links_and_images_resolve(doc: Path) -> None:
    text = _strip_code(doc.read_text(encoding="utf-8"))
    missing = [
        t
        for t in _local_targets(text, LINK) + _local_targets(text, IMAGE)
        if t and not (doc.parent / t).exists()
    ]
    assert missing == [], f"broken local links in {doc.name}: {missing}"


def test_readme_uses_approved_banner() -> None:
    text = (ROOT / "README.md").read_text(encoding="utf-8")
    assert 'src="assets/safetylens-hero.png"' in text
    assert "placeholder" not in text.lower()
    png = (ROOT / "assets" / "safetylens-hero.png").read_bytes()
    assert png[:8] == b"\x89PNG\r\n\x1a\n"


def test_readme_states_findings_pending() -> None:
    text = (ROOT / "README.md").read_text(encoding="utf-8")
    assert "Validated v1 research findings are pending" in text


def test_readme_diagram_matches_source() -> None:
    blocks = MERMAID.findall((ROOT / "README.md").read_text(encoding="utf-8"))
    source = (ROOT / "docs" / "diagrams" / "architecture.mmd").read_text(encoding="utf-8")
    assert blocks == [source]
    assert (ROOT / "docs" / "diagrams" / "architecture.png").exists()


@pytest.mark.parametrize(
    "pattern",
    [
        r"\w@",  # Mermaid 11 edge-ID syntax: the original rendering failure
        r"<br\s*/?>",  # HTML in labels: renderer-dependent
        r"\s&\s",  # combined-node edges: version-dependent
    ],
)
def test_mermaid_avoids_fragile_syntax(pattern: str) -> None:
    source = (ROOT / "docs" / "diagrams" / "architecture.mmd").read_text(encoding="utf-8")
    assert re.search(pattern, source) is None


def test_mermaid_labels_are_quoted() -> None:
    source = (ROOT / "docs" / "diagrams" / "architecture.mmd").read_text(encoding="utf-8")
    # Every node shape opener must be followed by a quoted label.
    for m in re.finditer(r"\w+(?:\[\(|\(\(|\[(?!\()|\{)(?!\")", source):
        pytest.fail(f"unquoted node label near: {source[m.start() : m.start() + 30]!r}")


def test_fragile_syntax_guard_catches_original_failure() -> None:
    original_label = "H[(Archive<br/>safetylens-research@b5d0dba)]"
    assert re.search(r"\w@", original_label)
    assert re.search(r"<br\s*/?>", original_label)


def test_link_checker_ignores_code_but_catches_real_links(tmp_path: Path) -> None:
    text = (
        'Quoted `<img src="nope.png">` and\n```text\n[x](missing.md)\n```\n'
        "Real [broken](gone.md) and ![img](absent.png)"
    )
    stripped = _strip_code(text)
    targets = _local_targets(stripped, LINK) + _local_targets(stripped, IMAGE)
    assert targets == ["gone.md", "absent.png"]
