from __future__ import annotations

from app.agents import available_archetypes


def validate_sequence(archetypes: list[str]) -> list[str]:
    """Validate an ordered archetype composition.

    Rules: non-empty, no duplicates, all registered, and the last archetype
    must be the analyst (`justice`) so the run can close.
    """
    if not archetypes:
        raise ValueError("At least one archetype is required")

    registered = set(available_archetypes())

    if len(set(archetypes)) != len(archetypes):
        raise ValueError("Archetypes must not repeat")

    for key in archetypes:
        if key not in registered:
            raise ValueError(f"Unknown archetype: {key}")

    if archetypes[-1] != "justice":
        raise ValueError("The last archetype must be 'justice' (analyst)")

    return archetypes
