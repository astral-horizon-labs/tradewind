#!/usr/bin/env python3
"""Calendrier des barres de prix : périodes, règlement, fenêtres calendaires."""
from __future__ import annotations
import datetime
import functools


def equity_week_start(stamp):
    """Rattache un début dominical IBKR à la semaine boursière qui suit."""
    day = datetime.date.fromisoformat(stamp[:10])
    return (day + datetime.timedelta(days=1 if day.weekday() == 6 else 0)).isoformat()








@functools.lru_cache(maxsize=65536)
def bar_period(ts, bar):
    """Clé de période : date en 1D, semaine ISO en 1W, mois en 1M."""
    if bar == "1D":
        return ts[:10]
    if bar == "1M":
        return ts[:7]
    y, w, _ = datetime.date.fromisoformat(ts[:10]).isocalendar()
    return f"{y}-W{w:02d}"


def month_closes(bar):
    """Clôtures réglées + dernier prix, sans retirer un mois déjà terminé."""
    per = {}
    for ts, c in zip(bar["t"], bar["c"]):
        per[ts[:7]] = c
    complete = [per[m] for m in month_keys(bar)]
    return complete, bar["c"][-1]


def period_end(timestamp, bar, week_ends_sunday=False):
    """Fin calendaire commune : séance, vendredi/dimanche, ou dernier jour du mois."""
    return _period_end(timestamp[:10], bar, bool(week_ends_sunday))


@functools.lru_cache(maxsize=65536)
def _period_end(day, bar, week_ends_sunday):
    date = datetime.date.fromisoformat(day)
    if bar == "1D":
        return date
    if bar == "1W":
        return date + datetime.timedelta(days=(6 if week_ends_sunday else 4) - date.weekday())
    following = datetime.date(date.year + (date.month == 12), date.month % 12 + 1, 1)
    return following - datetime.timedelta(days=1)


@functools.lru_cache(maxsize=65536)
def _period_end_iso(day, bar, week_ends_sunday):
    """`period_end` en chaîne ISO : l'ordre des chaînes AAAA-MM-JJ est celui des dates."""
    return _period_end(day, bar, week_ends_sunday).isoformat()


def completed_series(bars, bar, as_of=None, week_ends_sunday=False):
    """Clôtures 1W/1M réglées, une par période, avec provenance conservée."""
    cutoff = datetime.date.fromisoformat(str(as_of or datetime.date.today())[:10])
    if bars.get("as_of"):
        cutoff = min(cutoff, datetime.date.fromisoformat(str(bars["as_of"])[:10]))
    periods = {bar_period(stamp, bar): (stamp, close)
               for stamp, close in zip(bars.get("t", []), bars.get("c", []))}
    boundary = bars.get("settled_through")
    fetched = bars.get("fetched")


    cutoff_iso = cutoff.isoformat()
    fetched_iso = str(fetched)[:10] if fetched else None
    sunday = bool(week_ends_sunday)
    result = []
    for key, (stamp, close) in sorted(periods.items()):
        end_iso = _period_end_iso(stamp[:10], bar, sunday)
        if end_iso >= cutoff_iso:
            continue
        if boundary:
            complete = key <= bar_period(boundary, bar)
        elif fetched:



            complete = fetched_iso > end_iso
        else:
            complete = key < max(periods)
        if complete:
            result.append((stamp, close))
    return result


def month_keys(bar):
    """Mois réglés alignés sur month_closes ; la dernière barre n'est pas forcément partielle."""
    return [stamp[:7] for stamp, _close in completed_series(bar, "1M")]


def bars_through(bar, as_of=None):
    """Copie d'une série bornée à une date, sans écrire dans le cache."""
    if as_of is None:
        return bar
    cutoff = as_of.isoformat() if hasattr(as_of, "isoformat") else str(as_of)
    kept = [index for index, stamp in enumerate(bar.get("t", []))
            if stamp[:10] <= cutoff]
    if not kept:
        return None
    out = dict(bar)
    out["as_of"] = min(out.get("as_of", cutoff[:10]), cutoff[:10])
    for key in ("t", "c", "h", "l", "o"):
        values = bar.get(key)
        if isinstance(values, list):
            out[key] = [values[index] for index in kept]
    return out


def shift_month(month, k):
    """'AAAA-MM' reculé de k mois."""
    y, m = map(int, month.split("-"))
    n = y * 12 + (m - 1) - k
    return f"{n // 12:04d}-{n % 12 + 1:02d}"


def calendar_return(keys, closes, k):
    """Rendement en % sur k mois CALENDAIRES, ou None si la fenêtre est trouée."""
    if len(closes) <= k or keys[-1 - k] != shift_month(keys[-1], k):
        return None
    return (closes[-1] / closes[-1 - k] - 1) * 100


def weeks_apart(start, end, k, tolerance=6):
    """`end` tombe-t-il à k semaines CALENDAIRES de `start` (± `tolerance` jours) ?"""
    gap = (datetime.date.fromisoformat(str(end)[:10])
           - datetime.date.fromisoformat(str(start)[:10])).days
    return abs(gap - 7 * k) <= tolerance
