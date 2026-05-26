"""Ground prompt builder — evidence blocks must include Tavily snippets."""

from __future__ import annotations

from generator.prompts.ground import build_ground_messages
from generator.schema import Publisher, Source, SourceRights


def _source(sid: str, summary: str | None) -> Source:
    return Source(
        id=sid,
        url=f"https://reuters.com/{sid}",
        publisher=Publisher(name="Reuters", tier="T0"),
        title=f"Article {sid}",
        published_at="2026-05-14T08:00:00Z",
        fetched_at="2026-05-14T09:00:00Z",
        language="en",
        rights=SourceRights(max_excerpt_words=10000, can_paraphrase=True),
        summary=summary,
    )


def test_evidence_block_includes_snippet_when_summary_present():
    msgs = build_ground_messages(
        "Trump visits China",
        [_source("src_a1", "Trump landed in Beijing on Thursday for trade talks.")],
    )
    user_msg = msgs[-1]["content"]
    assert "Snippet: Trump landed in Beijing on Thursday" in user_msg


def test_evidence_block_omits_snippet_line_when_summary_missing():
    msgs = build_ground_messages("x", [_source("src_a1", None)])
    user_msg = msgs[-1]["content"]
    assert "Snippet:" not in user_msg
    # Trailing structure should still close cleanly.
    assert user_msg.count("</evidence>") == 1


def test_long_snippet_is_truncated_with_ellipsis():
    long_text = "ABCD" * 400  # 1600 chars
    msgs = build_ground_messages("x", [_source("src_a1", long_text)])
    user_msg = msgs[-1]["content"]
    # 600-char budget; truncated snippet ends with the ellipsis marker.
    assert "…" in user_msg
    # Sanity: the rendered block can't contain the entire 1600-char string.
    assert long_text not in user_msg


def test_grounding_rule_is_present_in_system_prompt():
    msgs = build_ground_messages("x", [])
    system_text = "\n".join(m["content"] for m in msgs if m["role"] == "system")
    assert "Grounding rule" in system_text
    assert "prior knowledge" in system_text
