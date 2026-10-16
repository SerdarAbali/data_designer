"""Deterministic, scope-aware demo workspace generator."""

from .generator import (
    DEMO_VERSION,
    PRESET_LABELS,
    PRESETS,
    demo_status,
    generate_demo,
    purge_demo,
    reset_demo,
    resolve_preset,
)

__all__ = [
    "DEMO_VERSION",
    "PRESETS",
    "PRESET_LABELS",
    "demo_status",
    "generate_demo",
    "purge_demo",
    "reset_demo",
    "resolve_preset",
]
