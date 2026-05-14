"""Schema-roundtrip smoke tests."""

from __future__ import annotations

from generator.schema import EventPage


def _minimal_page_dict() -> dict:
    return {
        "page_id": "page_test",
        "input_sentence": "Test event happened.",
        "generated_at": "2026-05-13T12:00:00Z",
        "subject": {
            "primary_entity": "Test Entity",
            "event_type_hint": "product_launch",
            "temporal_posture": "recent",
            "time_anchor": "2026-05-01T00:00:00Z",
        },
        "modules": [
            {
                "kind": "hero",
                "module_id": "mod_hero",
                "serves_needs": ["what_happened"],
                "citations": [{"source_id": "src_001", "claim_text": "A claim."}],
                "confidence": {
                    "overall": 0.9,
                    "field_level": {},
                    "signals": {
                        "source_count": 1,
                        "publisher_count": 1,
                        "highest_tier": "T0",
                        "schema_passes": True,
                        "cross_source_agreement": 1.0,
                    },
                    "flags": [],
                },
                "slot": "hero",
                "artifact": "HeroBanner",
                "artifact_alternatives": [],
                "inclusion_reason": "required",
                "data": {
                    "title": "Test Hero Title",
                    "summary": "Test summary.",
                    "image_alt": "test",
                },
            }
        ],
        "layout": {"preset_id": "product_focus"},
        "sources": [
            {
                "id": "src_001",
                "url": "https://example.com/a",
                "publisher": {"name": "Example", "tier": "T0"},
                "title": "Example article",
                "published_at": "2026-05-01T00:00:00Z",
                "fetched_at": "2026-05-13T12:00:00Z",
                "language": "en",
                "rights": {"max_excerpt_words": 10000, "can_paraphrase": True},
            }
        ],
        "needs_coverage": {
            "what_happened": ["mod_hero"],
            "when_where": [],
            "who_involved": [],
            "current_state": [],
            "why_matters": [],
            "world_reaction": [],
            "what_can_do": [],
            "what_next": [],
        },
        "uncovered_needs": [
            "when_where",
            "who_involved",
            "current_state",
            "why_matters",
            "world_reaction",
            "what_can_do",
            "what_next",
        ],
        "meta": {
            "last_updated": "2026-05-13T12:00:00Z",
            "editor_approved": True,
            "pipeline_trace_id": "trace_test",
        },
    }


def test_event_page_roundtrip() -> None:
    data = _minimal_page_dict()
    page = EventPage.model_validate(data)
    redump = page.model_dump(mode="json", exclude_none=True)
    # Roundtrip back through validation must succeed.
    EventPage.model_validate(redump)
    assert page.modules[0].kind == "hero"
    assert page.layout.preset_id == "product_focus"


def test_stage_trace_accepts_llm_calls():
    from generator.schema import StageTrace, LLMCall

    st = StageTrace(
        stage="triage",
        started_at="2026-05-13T12:00:00Z",
        duration_ms=120,
        outcome="success",
        llm_calls=[
            LLMCall(
                model="anthropic/claude-haiku-4-5",
                input_tokens=512,
                output_tokens=128,
                cost_usd=0.0011,
                duration_ms=110,
            )
        ],
    )
    assert st.llm_calls[0].model == "anthropic/claude-haiku-4-5"


def test_discriminated_union_rejects_unknown_kind() -> None:
    import pytest
    from pydantic import ValidationError

    data = _minimal_page_dict()
    data["modules"][0]["kind"] = "not_a_real_kind"
    with pytest.raises(ValidationError):
        EventPage.model_validate(data)


def test_hero_data_accepts_overview_bullets():
    from generator.schema import HeroData, OverviewBullet

    bullets = [OverviewBullet(text="Point one.", source_id="s1") for _ in range(3)]
    hd = HeroData(title="t", summary="s", image_alt="", overview_bullets=bullets)
    assert len(hd.overview_bullets) == 3


def test_hero_data_overview_bullets_optional():
    from generator.schema import HeroData

    hd = HeroData(title="t", summary="s", image_alt="")
    assert hd.overview_bullets is None


def test_overview_bullet_text_capped_at_18_words():
    import pytest
    from pydantic import ValidationError
    from generator.schema import OverviewBullet

    with pytest.raises(ValidationError):
        OverviewBullet(text=" ".join(["w"] * 19), source_id="s1")


def test_need_plan_category_defaults_none():
    from generator.schema import NeedCurationPlan

    p = NeedCurationPlan(
        need_id="what_happened",
        activated=True,
        rank=1,
        section_title="t",
        rationale="r",
    )
    assert p.category is None
    assert p.opinion_subtag is None


def test_reaction_item_stakeholder_tier_optional():
    from generator.schema import ReactionItem

    r = ReactionItem(
        author="A", author_role="role", quote="q",
        sentiment="positive", source_id="s1",
    )
    assert r.stakeholder_tier is None
    assert r.author_image_url is None


def test_reaction_item_accepts_stakeholder_tier():
    from generator.schema import ReactionItem

    r = ReactionItem(
        author="A", author_role="role", quote="q",
        sentiment="positive", source_id="s1",
        stakeholder_tier="stakeholder",
        author_image_url="https://x.test/a.jpg",
    )
    assert r.stakeholder_tier == "stakeholder"
    assert str(r.author_image_url).startswith("https://")
