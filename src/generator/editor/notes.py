"""Helpers for threading EditorNotes through downstream stage prompts."""

from __future__ import annotations

from generator.schema import EditorNotes


def merge_note(section_id: str, notes: EditorNotes | None) -> str | None:
    """Combine the per-section comment with the global comment for `section_id`.

    Returns None if both are absent. Format is stable so prompt builders can
    inject it verbatim.
    """
    if notes is None:
        return None
    per = notes.section_comments.get(section_id)
    glb = notes.global_comment
    if per and glb:
        return f"{per}\n\nGeneral note: {glb}"
    return per or glb or None


__all__ = ["merge_note"]
