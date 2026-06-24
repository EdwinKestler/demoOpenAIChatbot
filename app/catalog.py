"""Shared hardware catalog anchors for routing and vision classification."""

from __future__ import annotations

HARDWARE_ANCHORS: frozenset[str] = frozenset(
    {
        "martillo",
        "taladro",
        "broca",
        "lija",
        "tornillo",
        "pintura",
        "manguera",
        "tubería",
        "tuberia",
        "pvc",
        "guantes",
        "casco",
        "silicón",
        "silicon",
        "cinta",
        "escuadra",
        "tuerca",
        "perno",
        "alicate",
        "destornillador",
        "sierra",
        "pegamento",
        "adhesivo",
        "cemento",
        "yeso",
        "lamina",
        "cable",
        "multímetro",
        "multimetro",
        "escalera",
        "llave inglesa",
    }
)


def hardware_anchors_prompt_list() -> str:
    """Comma-separated anchor list for LLM vision prompts."""
    return ", ".join(sorted(HARDWARE_ANCHORS))