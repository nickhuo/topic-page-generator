from generator.pipeline.trace import TraceRecorder
from generator.schema import EditorAction


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
