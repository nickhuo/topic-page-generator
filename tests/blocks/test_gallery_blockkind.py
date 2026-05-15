"""Gallery: 8th BlockKind."""

from generator.schema import BlockKind


def test_gallery_is_valid_block_kind():
    from typing import get_args
    assert "gallery" in get_args(BlockKind)
