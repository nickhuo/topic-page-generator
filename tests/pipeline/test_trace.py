from generator.pipeline.trace import TraceRecorder
from generator.schema import (
    AcceptanceCriteria,
    EditorAction,
    ResearchEvalResult,
    SectionPlan,
    SectionResearchLog,
    SectionResearchStep,
)


def test_recorder_persists_editor_actions(tmp_path):
    rec = TraceRecorder(input_sentence="x", page_id="p1")
    rec.record_editor_action(
        EditorAction(
            action_at="2026-05-14T00:00:00Z",
            actor="editor:nick",
            action="approve_page",
            reason="looks good",
        )
    )
    trace = rec.finalize(auto_mode=False)
    assert len(trace.editor_actions) == 1
    assert trace.editor_actions[0].action == "approve_page"


def _plan(section_id: str) -> SectionPlan:
    return SectionPlan(
        section_id=section_id,
        kind="curated",
        title=section_id,
        rank=5,
        block_kind="paragraph",
        intent="explain",
        acceptance=AcceptanceCriteria(description="needs sources", min_sources=2),
    )


def test_stage_handle_records_curation_plan():
    rec = TraceRecorder(input_sentence="x", page_id="p1")
    with rec.stage("curation") as st:
        st.section_plans = [_plan("overview"), _plan("reactions")]
    stage = rec.stages[-1]
    assert stage.planning is not None
    assert [p.section_id for p in stage.planning.section_plans] == [
        "overview",
        "reactions",
    ]
    # Acceptance criteria ride along with the plan.
    assert stage.planning.section_plans[0].acceptance.min_sources == 2
    assert stage.planning.research_log == []


def test_stage_handle_records_research_log():
    rec = TraceRecorder(input_sentence="x", page_id="p1")
    with rec.stage("research") as st:
        st.research_log = [
            SectionResearchLog(
                section_id="overview",
                steps=[
                    SectionResearchStep(
                        iteration=1,
                        query="overview latest",
                        pool_size=3,
                        eval=ResearchEvalResult(satisfied=True),
                    )
                ],
            )
        ]
    stage = rec.stages[-1]
    assert stage.planning is not None
    assert [log.section_id for log in stage.planning.research_log] == ["overview"]
    assert stage.planning.research_log[0].steps[0].query == "overview latest"


def test_stage_without_planning_leaves_field_none():
    rec = TraceRecorder(input_sentence="x", page_id="p1")
    with rec.stage("render"):
        pass
    assert rec.stages[-1].planning is None
