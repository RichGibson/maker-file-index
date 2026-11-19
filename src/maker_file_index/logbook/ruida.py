"""Decode speed and power settings from a Ruida controller byte stream.

LightBurn's debug log records the bytes it sends to the laser. Ruida
scrambles each byte; after unscrambling, commands are an opcode byte
(high bit set) followed by 7-bit data bytes.
"""

from __future__ import annotations

from dataclasses import dataclass

MAGIC = 0x88


def _swap_bits_7_0(b: int) -> int:
    return (b & 0x7E) | ((b & 0x80) >> 7) | ((b & 0x01) << 7)


def unswizzle(b: int, magic: int = MAGIC) -> int:
    b = ((b - 1) & 0xFF) ^ magic
    return _swap_bits_7_0(b)


def swizzle(b: int, magic: int = MAGIC) -> int:
    return ((_swap_bits_7_0(b) ^ magic) + 1) & 0xFF


@dataclass(frozen=True)
class Setting:
    speed_mm_s: float
    min_power: float
    max_power: float


def _num(data: bytes) -> int:
    v = 0
    for x in data:
        v = (v << 7) | (x & 0x7F)
    return v


def _speed(data: bytes) -> float:
    return _num(data) / 1000


def _power(data: bytes) -> float:
    return round(_num(data) * 100 / 0x3FFF, 1)


def decode_settings(raw: bytes) -> list[Setting]:
    """Distinct settings in first-seen order.

    Body commands (layer select, then speed and powers) are authoritative.
    Header layer definitions fill in only layers never selected in the body.
    """
    d = bytes(unswizzle(b) for b in raw)
    header: dict[int, dict[str, float]] = {}
    body_layers: set[int] = set()
    found: list[Setting] = []
    pending: dict[str, float] | None = None
    n = len(d)
    i = 0

    def add(s: Setting) -> None:
        if s not in found:
            found.append(s)

    while i < n:
        op = d[i]
        sub = d[i + 1] if i + 1 < n else -1
        if op == 0xCA and sub == 0x02 and i + 2 < n:
            body_layers.add(d[i + 2])
            pending = {}
            i += 3
            continue
        if op == 0xC9 and sub == 0x04 and i + 8 <= n:
            header.setdefault(d[i + 2], {})["speed"] = _speed(d[i + 3:i + 8])
            i += 8
            continue
        if op == 0xC6 and sub in (0x31, 0x32) and i + 5 <= n:
            key = "min" if sub == 0x31 else "max"
            header.setdefault(d[i + 2], {})[key] = _power(d[i + 3:i + 5])
            i += 5
            continue
        if op == 0xC9 and sub == 0x02 and i + 7 <= n:
            if pending is not None:
                pending["speed"] = _speed(d[i + 2:i + 7])
            i += 7
            continue
        if op == 0xC6 and sub in (0x01, 0x02) and i + 4 <= n:
            if pending is not None:
                pending["min" if sub == 0x01 else "max"] = _power(d[i + 2:i + 4])
                if {"speed", "min", "max"} <= pending.keys():
                    add(Setting(pending["speed"], pending["min"], pending["max"]))
                    pending = None
            i += 4
            continue
        i += 1

    for layer in sorted(header):
        h = header[layer]
        if layer not in body_layers and {"speed", "min", "max"} <= h.keys():
            add(Setting(h["speed"], h["min"], h["max"]))
    return found


def grid(settings: list[Setting]) -> tuple[list[float], list[float]] | None:
    """(speeds, powers) when constant-power settings cover a full grid of at least 3x3."""
    flat = {(s.speed_mm_s, s.max_power) for s in settings if s.min_power == s.max_power}
    speeds = sorted({v for v, _ in flat})
    powers = sorted({p for _, p in flat})
    if len(speeds) < 3 or len(powers) < 3:
        return None
    if all((v, p) in flat for v in speeds for p in powers):
        return speeds, powers
    return None
