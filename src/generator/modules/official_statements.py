"""Official Statements module — direct quotes from named officials."""

from __future__ import annotations

from typing import ClassVar

from generator.modules.base import Module
from generator.schema import OfficialStatementsData


class OfficialStatementsModule(Module):
    kind: ClassVar[str] = "official_statements"
    serves_needs: ClassVar[list] = ["who_involved"]
    allowed_artifacts: ClassVar[list[str]] = ["StatementsList"]
    data_schema: ClassVar[type] = OfficialStatementsData

    extraction_prompt_template: ClassVar[str] = """\
You are extracting structured data for the "Official Statements" module of a news topic page.

Subject: {title}
Entities: {entities}

Evidence pool (each line is "[source_id] (tier publisher, published_at) title :: url"):
{evidence_block}

Task:
- Extract direct quotes from named officials, executives, or public figures only.
- Each statement needs: author name, role (e.g. "Secretary of State"), organization, verbatim quote, made_at (ISO 8601 timestamp when stated), source_url, and source_id.
- Skip paraphrased statements — only include verbatim direct quotes.
- Skip anonymous or unnamed sources.

Rules:
- Cite every fact via a source_id that appears in the evidence pool above.
- Do not invent facts not supported by the evidence.
- Output strictly conforms to the JSON schema you've been given.
"""

    def should_render(self, data: OfficialStatementsData | None) -> bool:  # type: ignore[override]
        if data is None:
            return False
        return len(data.items) >= 1
