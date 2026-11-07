"""Graphique hebdomadaire en PNG, en bibliothèque standard seule.

POURQUOI (2026-11-07). Le serveur du propriétaire capture le graphique du dashboard
(`chart_capture.mjs`, Playwright) ; un client n'a ni dashboard ni navigateur piloté.
« Le graphique d'abord » vaut pour lui aussi : l'assistant doit REGARDER une image,
pas lire une liste de clôtures. Ce module dessine donc les bougies lui-même, sans
dépendance à installer (ni matplotlib, ni Node), ce qui garde le MCP client
installable d'une ligne.

Échelle logarithmique, comme le dashboard. L'image ne porte aucun texte (pas de
police en bibliothèque standard) : les prix des lignes horizontales sont rendus à
côté de l'image, dans la réponse de l'outil, dans le même ordre, de haut en bas.
"""
from __future__ import annotations

import math
import struct
import zlib

WIDTH, HEIGHT = 960, 440
MARGIN_X, MARGIN_Y = 16, 16
BACKGROUND = (255, 255, 255)
GRID = (226, 226, 226)
UP = (22, 135, 90)
DOWN = (200, 50, 50)
COST = (40, 90, 210)
#: Couleur d'un niveau de plan par son effet : sortie et allègement en orange, renfort en
#: vert foncé, le reste (alerte, revue) en gris.
LEVEL_COLORS = {"exit": (230, 120, 0), "trim": (230, 120, 0), "add": (0, 110, 60)}
LEVEL_OTHER = (120, 120, 120)


def nice_levels(low: float, high: float, count: int = 6) -> list[float]:
    """Des prix ronds répartis entre `low` et `high`, du plus haut au plus bas."""
    if low <= 0 or high <= low:
        return [high]
    raw = (high - low) / count
    magnitude = 10 ** math.floor(math.log10(raw))
    step = next(m * magnitude for m in (1, 2, 2.5, 5, 10) if m * magnitude >= raw)
    level = math.ceil(low / step) * step
    levels = []
    while level <= high:
        levels.append(round(level, 10))
        level += step
    return sorted(levels, reverse=True)


class Canvas:
    def __init__(self, width: int, height: int):
        self.width, self.height = width, height
        self.pixels = bytearray(bytes(BACKGROUND) * (width * height))

    def fill(self, x0: int, y0: int, x1: int, y1: int, color: tuple[int, int, int]) -> None:
        x0, x1 = sorted((max(0, x0), min(self.width - 1, x1)))
        y0, y1 = sorted((max(0, y0), min(self.height - 1, y1)))
        row = bytes(color) * (x1 - x0 + 1)
        for y in range(y0, y1 + 1):
            start = (y * self.width + x0) * 3
            self.pixels[start:start + len(row)] = row

    def png(self) -> bytes:
        stride = self.width * 3
        raw = b"".join(b"\x00" + bytes(self.pixels[y * stride:(y + 1) * stride])
                       for y in range(self.height))

        def chunk(kind: bytes, data: bytes) -> bytes:
            return (struct.pack(">I", len(data)) + kind + data
                    + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF))

        header = struct.pack(">IIBBBBB", self.width, self.height, 8, 2, 0, 0, 0)
        return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", header)
                + chunk(b"IDAT", zlib.compress(raw, 9)) + chunk(b"IEND", b""))


def weekly_png(bars: list[dict], cost: float | None = None,
               levels: list[dict] | None = None) -> tuple[bytes, list[float]]:
    """(PNG, prix des lignes de la grille de haut en bas). `bars` : {o, h, l, c} datées ;
    `levels` : seuils du plan {px, effect}, tracés en trait plein de trois pixels."""
    levels = [level for level in (levels or []) if level.get("px") and level["px"] > 0]
    extra = ([cost] if cost else []) + [level["px"] for level in levels]
    lows = [bar["l"] for bar in bars if bar["l"] > 0]
    highs = [bar["h"] for bar in bars]
    low, high = min(lows + extra), max(highs + extra)
    low, high = low * 0.97, high * 1.03
    top, bottom = MARGIN_Y, HEIGHT - MARGIN_Y
    left, right = MARGIN_X, WIDTH - MARGIN_X

    def y_of(price: float) -> int:
        share = (math.log(high) - math.log(max(price, low))) / (math.log(high) - math.log(low))
        return round(top + share * (bottom - top))

    canvas = Canvas(WIDTH, HEIGHT)
    grid = nice_levels(low, high)
    for price in grid:
        y = y_of(price)
        canvas.fill(left, y, right, y, GRID)
    for level in levels:
        y = y_of(level["px"])
        canvas.fill(left, y - 1, right, y + 1, LEVEL_COLORS.get(level.get("effect"), LEVEL_OTHER))
    if cost:
        y = y_of(cost)
        for x in range(left, right, 12):
            canvas.fill(x, y - 1, x + 7, y, COST)
    slot = (right - left) / max(len(bars), 1)
    body = max(1, int(slot * 0.6))
    for index, bar in enumerate(bars):
        color = UP if bar["c"] >= bar["o"] else DOWN
        center = round(left + slot * (index + 0.5))
        canvas.fill(center, y_of(bar["h"]), center, y_of(bar["l"]), color)
        canvas.fill(center - body // 2, y_of(max(bar["o"], bar["c"])),
                    center - body // 2 + body - 1, y_of(min(bar["o"], bar["c"])), color)
    return canvas.png(), grid
