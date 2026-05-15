"""Hand-tuned palettes for the 4 aesthetic presets.

Each palette is a dict from CSS custom-property name to value. `palette_css_vars`
renders a `:root { ... }` block for inlining into <head>.
"""

from __future__ import annotations

from generator.schema import PaletteId

REQUIRED_VARS: frozenset[str] = frozenset(
    {
        "--color-bg",
        "--color-surface",
        "--color-ink",
        "--color-ink-muted",
        "--color-accent",
        "--color-accent-ink",
        "--color-divider",
        "--font-weight-body",
        "--font-weight-heading",
    }
)


PALETTES: dict[PaletteId, dict[str, str]] = {
    "festive_warm": {
        "--color-bg": "#fff8f1",
        "--color-surface": "#ffffff",
        "--color-ink": "#1a0f0a",
        "--color-ink-muted": "#6b4a3a",
        "--color-accent": "#b91c4b",
        "--color-accent-ink": "#ffffff",
        "--color-divider": "#f0d9c3",
        "--font-weight-body": "400",
        "--font-weight-heading": "700",
    },
    "minimal_tech": {
        "--color-bg": "#fafafa",
        "--color-surface": "#ffffff",
        "--color-ink": "#0a0a0a",
        "--color-ink-muted": "#5a5a5a",
        "--color-accent": "#2563eb",
        "--color-accent-ink": "#ffffff",
        "--color-divider": "#e5e5e5",
        "--font-weight-body": "400",
        "--font-weight-heading": "600",
    },
    "urgent_red": {
        "--color-bg": "#0a0a0a",
        "--color-surface": "#1a1a1a",
        "--color-ink": "#fafafa",
        "--color-ink-muted": "#a1a1a1",
        "--color-accent": "#dc2626",
        "--color-accent-ink": "#ffffff",
        "--color-divider": "#262626",
        "--font-weight-body": "400",
        "--font-weight-heading": "800",
    },
    "urgent_light": {
        "--color-bg": "#fbfaf7",
        "--color-surface": "#ffffff",
        "--color-ink": "#0a0a0a",
        "--color-ink-muted": "#525252",
        "--color-accent": "#dc2626",
        "--color-accent-ink": "#ffffff",
        "--color-divider": "#e7e5e4",
        "--font-weight-body": "400",
        "--font-weight-heading": "800",
    },
    "muted_solemn": {
        "--color-bg": "#f5f5f4",
        "--color-surface": "#ffffff",
        "--color-ink": "#1c2434",
        "--color-ink-muted": "#52606d",
        "--color-accent": "#334155",
        "--color-accent-ink": "#ffffff",
        "--color-divider": "#d6d3d1",
        "--font-weight-body": "400",
        "--font-weight-heading": "600",
    },
    "bold_sport": {
        "--color-bg": "#ffffff",
        "--color-surface": "#f8fafc",
        "--color-ink": "#0f172a",
        "--color-ink-muted": "#475569",
        "--color-accent": "#059669",
        "--color-accent-ink": "#ffffff",
        "--color-divider": "#e2e8f0",
        "--font-weight-body": "500",
        "--font-weight-heading": "800",
    },
    "neutral_news": {
        "--color-bg": "#fbfaf7",
        "--color-surface": "#ffffff",
        "--color-ink": "#171717",
        "--color-ink-muted": "#525252",
        "--color-accent": "#b91c1c",
        "--color-accent-ink": "#ffffff",
        "--color-divider": "#e7e5e4",
        "--font-weight-body": "400",
        "--font-weight-heading": "700",
    },
}


def palette_css_vars(palette_id: PaletteId) -> str:
    """Render a `:root { ... }` CSS block for the given palette."""
    pairs = PALETTES[palette_id]
    body = "\n".join(f"  {k}: {v};" for k, v in pairs.items())
    return f":root {{\n{body}\n}}"
