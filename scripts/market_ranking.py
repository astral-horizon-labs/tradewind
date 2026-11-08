"""Le classement de tous les paniers face au S&P 500, calculé là où vivent les séries."""
from __future__ import annotations

import datetime
import json
import pathlib

import data_root

ROOT = pathlib.Path(__file__).resolve().parent.parent
BASKETS_FILE = ROOT / "references" / "baskets.json"
BENCHMARK = "SPY"
WINDOWS = (4, 13, 26, 52)
SMA_WEEKS = 10
RANK_WEEKS = 13
LEADERS = 3

MARKET_KEYS = ("generated_at", "last_settled_week", "benchmark", "ranking_by", "legend", "baskets")
BASKET_KEYS = ("rank", "basket", "members", "members_with_series", "last_settled_week", "windows",
               "ratio_vs_sma10", "above_sma10", "trend_5w", "leaders_13w", "laggards_13w")


def change_pct(closes: list[float], weeks: int) -> float | None:
    if len(closes) <= weeks or not closes[-weeks - 1]:
        return None
    return round((closes[-1] / closes[-weeks - 1] - 1) * 100, 2)


def equal_weight(series: list[dict[str, float]]) -> dict[str, float]:
    """Indice équipondéré, base 100, des semaines communes à au moins la moitié des membres."""
    weeks = sorted({week for closes in series for week in closes})
    index, level, previous = {}, 100.0, None
    for week in weeks:
        present = [closes for closes in series if week in closes]
        if len(present) * 2 < len(series):
            continue
        if previous is not None:
            moves = [closes[week] / closes[previous] - 1 for closes in present
                     if previous in closes and closes[previous]]
            if moves:
                level *= 1 + sum(moves) / len(moves)
        index[week] = level
        previous = week
    return index


def ratio_reading(own: dict[str, float], bench: dict[str, float]) -> dict | None:
    """Le ratio d'une série à son repère : face à sa moyenne de dix semaines, et son sens."""
    common = sorted(set(own) & set(bench))
    if len(common) < SMA_WEEKS + 2:
        return None
    ratio = [own[week] / bench[week] for week in common]
    sma = sum(ratio[-SMA_WEEKS:]) / SMA_WEEKS
    recent = ratio[-5:]
    trend = "improving" if recent[-1] > recent[0] else "deteriorating" if recent[-1] < recent[0] else "flat"
    return {"ratio_vs_sma10": round(ratio[-1] / sma, 4), "above_sma10": ratio[-1] > sma, "trend_5w": trend}


def windows(own: dict[str, float], bench: dict[str, float]) -> dict:
    """Variation du panier et du repère sur 4 à 52 semaines, sur leurs semaines communes."""
    common = sorted(set(own) & set(bench))
    mine, theirs = [own[week] for week in common], [bench[week] for week in common]
    out = {}
    for weeks in WINDOWS:
        a, b = change_pct(mine, weeks), change_pct(theirs, weeks)
        out[f"{weeks}w"] = {"basket_pct": a, "benchmark_pct": b,
                            "spread_pts": round(a - b, 2) if None not in (a, b) else None}
    return out


def rank(baskets: dict[str, list[dict]], closes_by_conid: dict[int, dict[str, float]],
         bench: dict[str, float]) -> list[dict]:
    """Chaque panier qui a des séries, classé par écart sur 13 semaines face au repère."""
    rows = []
    for name, members in baskets.items():
        found = [(member, closes_by_conid.get(member.get("conid"))) for member in members]
        found = [(member, closes) for member, closes in found if closes]
        if not found:
            continue
        index = equal_weight([closes for _, closes in found])
        reading = ratio_reading(index, bench)
        if reading is None:
            continue
        strength = []
        for member, closes in found:
            values = [closes[week] for week in sorted(closes)]
            move = change_pct(values, RANK_WEEKS)
            if move is not None:
                strength.append({"symbol": member["symbol"], "change_13w_pct": move})
        strength.sort(key=lambda row: row["change_13w_pct"], reverse=True)
        rows.append({"basket": name, "members": len(members), "members_with_series": len(found),
                     "last_settled_week": max(index), "windows": windows(index, bench), **reading,
                     "leaders_13w": strength[:LEADERS],
                     "laggards_13w": list(reversed(strength[-LEADERS:])) if len(strength) > LEADERS else []})
    rows.sort(key=lambda row: (row["windows"]["13w"]["spread_pts"] is not None,
                               row["windows"]["13w"]["spread_pts"] or 0), reverse=True)
    return [{"rank": position, **row} for position, row in enumerate(rows, 1)]


def weekly_closes(path: pathlib.Path, today: datetime.date) -> dict[str, float]:
    """{semaine: clôture} réglée d'un fichier de série local, vide s'il est illisible."""
    import bar_calendar

    try:
        bars = json.loads(path.read_text(encoding="utf-8"))["bars"]["1W"]
    except (OSError, ValueError, KeyError, TypeError):
        return {}
    settled = {stamp for stamp, _ in bar_calendar.completed_series(bars, "1W", as_of=today)}
    closes = {}
    for stamp, close in zip(bars.get("t", []), bars.get("c", [])):
        if stamp in settled and close and close > 0:
            closes[stamp[:10]] = close
    return closes


def benchmark_conid() -> int | None:
    try:
        seed = json.loads(data_root.universe_seed_file().read_text(encoding="utf-8"))["instruments"]
    except (OSError, ValueError, KeyError):
        return None
    return (seed.get(BENCHMARK) or {}).get("conid")


def build(directory: pathlib.Path, today: datetime.date, *, baskets_file: pathlib.Path = BASKETS_FILE,
          now: datetime.datetime | None = None) -> dict | None:
    """Le classement à publier, ou None si le repère ou tout panier manque au cache."""
    try:
        baskets = json.loads(baskets_file.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    spy = benchmark_conid()
    bench = weekly_closes(directory / f"{spy}.json", today) if spy else {}
    if not bench:
        return None
    conids = {member["conid"] for members in baskets.values() for member in members if member.get("conid")}
    closes = {conid: weekly_closes(directory / f"{conid}.json", today) for conid in conids}
    rows = rank(baskets, {conid: found for conid, found in closes.items() if found}, bench)
    if not rows:
        return None
    now = now or datetime.datetime.now(datetime.timezone.utc)
    return {"generated_at": now.isoformat(timespec="seconds"), "last_settled_week": max(bench),
            "benchmark": BENCHMARK, "ranking_by": "windows.13w.spread_pts",
            "legend": ("each basket is an equal-weight index of its members, against SPY on settled "
                       "weekly closes; spread_pts is the basket's change minus SPY's in percentage "
                       "points; ratio_vs_sma10 above 1 means the basket leads SPY over its 10-week "
                       "average; trend_5w is the direction of that ratio over the last five weeks"),
            "baskets": rows}
