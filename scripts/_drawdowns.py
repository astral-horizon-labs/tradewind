#!/usr/bin/env python3
"""LA LOI DES BAISSES DEPUIS UN SOMMET — sous l'eau, pire point, épisodes."""
from __future__ import annotations

from collections.abc import Sequence


def underwater(values: Sequence[float]) -> list[float]:
    """Écart de chaque point à son plus-haut ANTÉRIEUR (point inclus), en %, toujours ≤ 0."""
    out: list[float] = []
    peak: float | None = None
    for value in values:
        if peak is None or value > peak:
            peak = value
        out.append((value / peak - 1) * 100)
    return out


def current(values: Sequence[float], dates: Sequence[str]) -> dict | None:
    """Baisse du DERNIER point depuis le plus-haut de toute la série."""
    if not dates:
        return None
    peak_index = max(range(len(values)), key=values.__getitem__)
    return {"pct": (values[-1] / values[peak_index] - 1) * 100,
            "peak_on": dates[peak_index], "last_on": dates[-1]}


def worst(values: Sequence[float], dates: Sequence[str]) -> tuple[float, str | None]:
    """(pire écart au plus-haut antérieur en %, sa date) ; (0.0, None) sans aucune baisse."""
    worst_pct, worst_on = 0.0, None
    for index, pct in enumerate(underwater(values)):
        if pct < worst_pct:
            worst_pct, worst_on = pct, dates[index]
    return worst_pct, worst_on


def episodes(values: Sequence[float], dates: Sequence[str], min_depth_pct: float = 0.0) -> list[dict]:
    """Chaque baisse, du dernier point au sommet jusqu'au premier retour à ce sommet."""
    found: list[dict] = []
    peak_index = 0
    episode: dict | None = None
    for index, value in enumerate(values):
        if value >= values[peak_index]:
            if episode is not None:
                episode["recovered_index"] = index
                found.append(episode)
                episode = None
            peak_index = index
            continue
        pct = (value / values[peak_index] - 1) * 100
        if episode is None:
            episode = {"peak_index": peak_index, "trough_index": index, "depth": pct,
                       "crossed_index": None, "recovered_index": None}
        if pct < episode["depth"]:
            episode["depth"], episode["trough_index"] = pct, index
        if episode["crossed_index"] is None and pct <= -min_depth_pct:
            episode["crossed_index"] = index
    if episode is not None:
        found.append(episode)
    out = []
    for item in found:
        if item["depth"] > -min_depth_pct:
            continue
        recovered = item["recovered_index"]
        out.append({
            "peak_on": dates[item["peak_index"]],
            "trough_on": dates[item["trough_index"]],
            "recovered_on": None if recovered is None else dates[recovered],
            "crossed_on": dates[item["crossed_index"]],
            "depth_pct": item["depth"],
            "open": recovered is None,
        })
    return out
