"""Module registry. Each subclass auto-registers via __init_subclass__."""
from __future__ import annotations
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from generator.modules.base import Module

MODULE_REGISTRY: dict[str, type["Module"]] = {}


def all_modules() -> list[type["Module"]]:
    # Eagerly import all module files so the registry is populated.
    from generator.modules import (
        hero, infobox, schedule, countdown, kpi_numbers, comparison,
        changelog, reactions, media_coverage, official_statements,
        where_to_watch, background,  # noqa: F401
    )
    return list(MODULE_REGISTRY.values())
