"""Palette resolution and perceptual derived-colour helpers.

Derived colours are resolved once, after YAML validation, so all renderers can
continue to consume ordinary CSS colour strings. Lighten/darken operations use
OKLCH lightness rather than naive per-channel RGB interpolation.
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from typing import Any


def resolve_palette_map(palette: Mapping[str, Any]) -> dict[str, str]:
    """Resolve a palette containing literal and derived colour entries.

    Literal strings are preserved. Derived objects are duck-typed so this module
    does not depend on the Pydantic schema and can therefore be used by it
    without an import cycle.
    """

    resolved: dict[str, str] = {}
    visiting: set[str] = set()

    def resolve(name: str) -> str:
        if name in resolved:
            return resolved[name]
        if name in visiting:
            cycle = " -> ".join([*visiting, name])
            raise ValueError(f"palette derivation cycle involving {cycle}")
        try:
            value = palette[name]
        except KeyError as exc:
            raise ValueError(f"derived palette colour references unknown colour {name!r}") from exc

        visiting.add(name)
        try:
            if isinstance(value, str):
                result = value
            else:
                source = getattr(value, "from_", None)
                if not source:
                    raise ValueError(f"unsupported palette value for {name!r}")
                base = resolve(str(source))
                lighten = getattr(value, "lighten", None)
                darken = getattr(value, "darken", None)
                if lighten is None and darken is None:
                    result = base
                elif lighten is not None:
                    result = adjust_oklch_lightness(base, float(lighten), lighten=True)
                else:
                    result = adjust_oklch_lightness(base, float(darken), lighten=False)
            resolved[name] = result
            return result
        finally:
            visiting.remove(name)

    for key in palette:
        resolve(str(key))
    return resolved


def adjust_oklch_lightness(colour: str, amount: float, *, lighten: bool) -> str:
    """Move OKLCH lightness toward white or black by ``amount`` (0..1)."""

    if not 0.0 <= amount <= 1.0:
        raise ValueError("palette lighten/darken amount must be between 0 and 1")
    red, green, blue = _parse_hex_colour(colour)
    L, a, b = _srgb_to_oklab(red, green, blue)
    chroma = math.hypot(a, b)
    hue = math.atan2(b, a)
    new_L = L + (1.0 - L) * amount if lighten else L * (1.0 - amount)
    new_a = chroma * math.cos(hue)
    new_b = chroma * math.sin(hue)
    rgb = _oklab_to_srgb(new_L, new_a, new_b)
    return "#" + "".join(f"{round(_clamp(channel) * 255):02x}" for channel in rgb)


def _parse_hex_colour(value: str) -> tuple[float, float, float]:
    text = value.strip()
    if len(text) == 4 and text.startswith("#"):
        text = "#" + "".join(character * 2 for character in text[1:])
    if len(text) != 7 or not text.startswith("#"):
        raise ValueError(
            f"derived palette colours currently require #RGB or #RRGGBB input, got {value!r}"
        )
    try:
        channels = tuple(int(text[index : index + 2], 16) / 255.0 for index in (1, 3, 5))
    except ValueError as exc:
        raise ValueError(f"invalid hex colour {value!r}") from exc
    return channels  # type: ignore[return-value]


def _srgb_to_linear(value: float) -> float:
    return value / 12.92 if value <= 0.04045 else ((value + 0.055) / 1.055) ** 2.4


def _linear_to_srgb(value: float) -> float:
    return 12.92 * value if value <= 0.0031308 else 1.055 * max(value, 0.0) ** (1.0 / 2.4) - 0.055


def _srgb_to_oklab(red: float, green: float, blue: float) -> tuple[float, float, float]:
    r = _srgb_to_linear(red)
    g = _srgb_to_linear(green)
    b = _srgb_to_linear(blue)

    l = 0.4122214708 * r + 0.5363325363 * g + 0.0514459929 * b
    m = 0.2119034982 * r + 0.6806995451 * g + 0.1073969566 * b
    s = 0.0883024619 * r + 0.2817188376 * g + 0.6299787005 * b

    l_ = math.copysign(abs(l) ** (1.0 / 3.0), l)
    m_ = math.copysign(abs(m) ** (1.0 / 3.0), m)
    s_ = math.copysign(abs(s) ** (1.0 / 3.0), s)

    return (
        0.2104542553 * l_ + 0.7936177850 * m_ - 0.0040720468 * s_,
        1.9779984951 * l_ - 2.4285922050 * m_ + 0.4505937099 * s_,
        0.0259040371 * l_ + 0.7827717662 * m_ - 0.8086757660 * s_,
    )


def _oklab_to_srgb(L: float, a: float, b: float) -> tuple[float, float, float]:
    l_ = L + 0.3963377774 * a + 0.2158037573 * b
    m_ = L - 0.1055613458 * a - 0.0638541728 * b
    s_ = L - 0.0894841775 * a - 1.2914855480 * b

    l = l_**3
    m = m_**3
    s = s_**3

    r = 4.0767416621 * l - 3.3077115913 * m + 0.2309699292 * s
    g = -1.2684380046 * l + 2.6097574011 * m - 0.3413193965 * s
    blue = -0.0041960863 * l - 0.7034186147 * m + 1.7076147010 * s
    return _linear_to_srgb(r), _linear_to_srgb(g), _linear_to_srgb(blue)


def _clamp(value: float) -> float:
    return min(1.0, max(0.0, value))
