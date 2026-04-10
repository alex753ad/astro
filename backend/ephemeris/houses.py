"""House systems module.

Provides helpers for house system selection and validation.
The actual computation is in calculator.py via swe.houses().
"""

from __future__ import annotations

SUPPORTED_SYSTEMS = {
    "placidus": "Placidus (default, most popular in Western astrology)",
    "koch": "Koch (popular in German-speaking countries)",
    "equal": "Equal House (each house = 30°)",
    "whole_sign": "Whole Sign (oldest system, Hellenistic)",
}


def get_supported_systems() -> dict[str, str]:
    """Return dict of supported house systems with descriptions."""
    return SUPPORTED_SYSTEMS.copy()


def validate_house_system(system: str) -> str:
    """Validate and normalize house system name."""
    system = system.lower().strip()
    if system not in SUPPORTED_SYSTEMS:
        raise ValueError(
            f"Unsupported house system: '{system}'. "
            f"Supported: {', '.join(SUPPORTED_SYSTEMS.keys())}"
        )
    return system
