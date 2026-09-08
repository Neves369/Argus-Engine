from __future__ import annotations

from app.agents import available_archetypes


def validate_sequence(archetypes: list[str]) -> list[str]:
    """Validate a card composition.

    Rules: non-empty, no duplicates, all registered, no ``emperor`` (the
    Imperador is the permanent supervisor, not a card — see GUIA_CARTAS), and
    the last archetype must be the analyst (``justice``) so the run can close.
    A ordem das cartas não define a ordem de execução (o grafo é sempre
    supervisionado) — ela é apenas o conjunto liberado ao Imperador.
    """
    if not archetypes:
        raise ValueError("At least one archetype is required")

    registered = set(available_archetypes())

    if len(set(archetypes)) != len(archetypes):
        raise ValueError("Archetypes must not repeat")

    for key in archetypes:
        if key not in registered:
            raise ValueError(f"Unknown archetype: {key}")

    if "emperor" in archetypes:
        raise ValueError("O Imperador não é uma carta jogável (rege todo run)")

    if archetypes[-1] != "justice":
        raise ValueError("The last archetype must be 'justice' (analyst)")

    return archetypes
