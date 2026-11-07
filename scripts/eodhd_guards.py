#!/usr/bin/env python3
"""Gardes EODHD : écarter une série suspecte SANS la recouper chez IBKR."""
from __future__ import annotations

import argparse
import concurrent.futures
import datetime
import json
import os
import pathlib
import statistics
import sys
import time

import bar_calendar
import data_root
import eodhd_history
import jsonio
import market_identity




REGISTRY = (pathlib.Path(os.environ["WALLET_EODHD_GUARDS"]) if os.environ.get("WALLET_EODHD_GUARDS")
            else data_root.book_refs() / "eodhd-guards.json")




SPLIT_JUMP = 1.8



SPLIT_SHAPE_TOLERANCE = 0.06




SPLIT_YEARS = 5

SPLIT_HOLD = 5


SPLIT_HOLD_TOLERANCE = 0.25



SPLIT_VOLUME_SURGE = 3.0


FLAT_DAYS = 5
FLAT_WINDOW = 24



WICK_GAP = 0.08




WICK_RANGE_MULTIPLE = 5.0

WICK_WINDOW = 504



WICK_ALLOWED = 2


COHERENCE_TOLERANCE = 0.005

PENNY_THRESHOLD = 1.0

GUARDS = ("named", "unavailable", "split", "incoherent", "flat", "wick", "penny")


def _day(bar):
    return datetime.datetime.fromtimestamp(
        bar["t"] / 1000, datetime.timezone.utc).date().isoformat()


def split_shaped(factor):
    """Vrai si le facteur (≥ 1) est à moins de 6 % d'un entier ou d'un demi-entier."""
    doubled = factor * 2
    return abs(doubled / round(doubled) - 1) <= SPLIT_SHAPE_TOLERANCE


def missing_splits(daily, today=None):
    """[(séance, facteur)] des sauts qui ont la forme d'un split oublié ou mal daté."""
    found = []
    today = today or datetime.date.today()
    since = (today - datetime.timedelta(days=round(365.25 * SPLIT_YEARS))).isoformat()
    closes = [bar.get("c") for bar in daily]
    for index in range(1, len(daily)):
        before, after = closes[index - 1], closes[index]
        if not before or not after:
            continue
        ratio = after / before
        factor = max(ratio, 1 / ratio)
        if factor < SPLIT_JUMP or not split_shaped(factor):
            continue
        day = _day(daily[index])
        if day < since:
            continue
        prior = [c for c in closes[max(0, index - SPLIT_HOLD):index] if c]
        later = [c for c in closes[index:index + SPLIT_HOLD] if c]
        if len(prior) < 2 or len(later) < 2:
            continue
        held = statistics.median(later) / statistics.median(prior)
        if abs(held / ratio - 1) > SPLIT_HOLD_TOLERANCE:
            continue
        volumes = [bar.get("v") or 0 for bar in daily[max(0, index - 20):index]]
        usual = statistics.median(volumes) if volumes else 0
        if usual and (daily[index].get("v") or 0) >= SPLIT_VOLUME_SURGE * usual:
            continue
        found.append((day, round(ratio, 4)))
    return found


def flat_days(daily, window=FLAT_WINDOW):
    """[séance] plates (o = h = l = c) dans la fenêtre récente."""
    return [_day(bar) for bar in daily[-window:]
            if bar.get("c") is not None
            and bar.get("o") == bar.get("h") == bar.get("l") == bar.get("c")]


def isolated_wicks(daily, window=WICK_WINDOW, gap=WICK_GAP):
    """[(séance, côté, écart)] des extrêmes loin du corps ET des voisines."""
    found = []
    start = max(1, len(daily) - window)
    for index in range(start, len(daily) - 1):
        bar, prev, nxt = daily[index], daily[index - 1], daily[index + 1]
        if None in (bar.get("o"), bar.get("c"), bar.get("h"), bar.get("l")):
            continue
        top, bottom = max(bar["o"], bar["c"]), min(bar["o"], bar["c"])
        ranges = [(item["h"] - item["l"]) / item["c"] for item in daily[max(0, index - 20):index]
                  if item.get("h") is not None and item.get("l") is not None and item.get("c")]
        usual = statistics.median(ranges) if ranges else 0
        if not usual:
            continue
        neighbours_high = max(prev.get("h") or 0, nxt.get("h") or 0)
        neighbours_low = min(prev.get("l") or float("inf"), nxt.get("l") or float("inf"))
        if top and neighbours_high and bar["h"] > top * (1 + gap) \
                and bar["h"] > neighbours_high * (1 + gap) \
                and bar["h"] / top - 1 >= WICK_RANGE_MULTIPLE * usual:
            found.append((_day(bar), "high", round(bar["h"] / top - 1, 4)))
        if bottom and neighbours_low != float("inf") and bar["l"] < bottom * (1 - gap) \
                and bar["l"] < neighbours_low * (1 - gap) \
                and 1 - bar["l"] / bottom >= WICK_RANGE_MULTIPLE * usual:
            found.append((_day(bar), "low", round(bar["l"] / bottom - 1, 4)))
    return found


def incoherent_periods(daily, bars, tag, tolerance=COHERENCE_TOLERANCE):
    """[(période, écart)] où la clôture agrégée n'est pas la dernière séance."""
    last = {}
    for bar in daily:
        if bar.get("c"):
            last[bar_calendar.bar_period(_day(bar), tag)] = bar["c"]
    found = []
    for bar in bars:
        period = bar_calendar.bar_period(_day(bar), tag)
        reference = last.get(period)
        if reference and bar.get("c") and abs(bar["c"] / reference - 1) > tolerance \
                and bar.get("rebuilt_from_daily") is not True:
            found.append((period, round(bar["c"] / reference - 1, 4)))
    return found


def judge(tf, splits=(), *, named=None, today=None):
    """Verdict d'une série : {"ok", "flags": [{guard, detail, periods}]}."""
    flags = []

    def flag(guard, detail, periods=()):
        flags.append({"guard": guard, "detail": detail, "periods": list(periods)[-6:]})

    if named:
        flag("named", named)
    transient = [value["error"] for value in tf.values()
                 if isinstance(value, dict) and value.get("status") != 404]
    if transient:

        return {"ok": None, "unmeasured": transient[0], "flags": flags}
    daily = tf.get("1D")
    if not isinstance(daily, list) or not daily:
        flag("unavailable", (daily or {}).get("error", "série quotidienne vide")
             if isinstance(daily, dict) else "série quotidienne vide")
        return {"ok": False, "flags": flags}
    jumps = missing_splits(daily, today)
    if jumps:
        declared = f" ; splits déclarés : {', '.join(f'{d} ×{f:g}' for d, f in splits[-2:])}" \
            if splits else ""
        flag("split", f"{len(jumps)} saut(s) en forme de split, dernier ×{jumps[-1][1]:g}{declared}",
             [day for day, _ in jumps])
    for tag in ("1W", "1M"):
        bars = tf.get(tag)
        if not isinstance(bars, list) or not bars:
            flag("unavailable", f"série {tag} absente")
            continue
        wrong = incoherent_periods(daily, bars, tag)


        if len(wrong) >= 2:
            worst = max(wrong, key=lambda item: abs(item[1]))
            flag("incoherent", f"{tag} : {len(wrong)} clôture(s) hors de la dernière séance, "
                 f"jusqu'à {worst[1]:+.1%}", [period for period, _ in wrong])
    flat = flat_days(daily)
    if len(flat) >= FLAT_DAYS:
        flag("flat", f"{len(flat)} séances plates sur les {FLAT_WINDOW} dernières", flat)
    wicks = isolated_wicks(daily)
    if len(wicks) > WICK_ALLOWED:
        worst = max(wicks, key=lambda item: abs(item[2]))
        flag("wick", f"{len(wicks)} mèches isolées sur deux ans, jusqu'à {worst[2]:+.1%}",
             [day for day, _, _ in wicks])
    last = next((bar["c"] for bar in reversed(daily) if bar.get("c")), None)
    if last is not None and abs(last) < PENNY_THRESHOLD:
        flag("penny", f"dernière clôture {last:g} sous {PENNY_THRESHOLD:g} $")
    return {"ok": not flags, "flags": flags}




def _excluded_code(entry):
    """Le code d'une série exclue, tiré de son motif (« code XXX.US exclu : … »)."""
    reason = entry.get("eodhd_unresolved") or ""
    if reason.startswith("code ") and " exclu" in reason:
        return reason[5:].split(" ", 1)[0]
    return None


def targets(table=None):
    """[(conid, symbole, code, diviseur, motif nommé)] de toute la table d'identité."""
    table = market_identity.load() if table is None else table
    found = []
    for conid, entry in sorted(table.items()):
        row = market_identity.symbol_for(conid, "eodhd", table=table)
        named = market_identity.EODHD_EXCLUDED.get(conid)
        code = row["symbol"] if row else (_excluded_code(entry) if named else None)
        if not code:
            continue
        found.append((conid, entry.get("symbol"), code,
                      (row or {}).get("divisor", 1), named))
    return found




RETRIES = 4
RETRY_PAUSE = 10


def fetch_series(code, divisor=1, *, key, today=None, sleep=time.sleep):
    """{"1D", "1W", "1M"} complets et ajustés, plus les splits déclarés en vigueur."""
    tf, meta = {}, {}
    for tag in ("1D", "1W", "1M"):
        for attempt in range(RETRIES + 1):
            try:
                tf[tag] = eodhd_history.fetch_symbol(code, tag, "60y", key=key, metadata=meta,
                                                     divisor=divisor, today=today)
                break
            except Exception as exc:
                status = getattr(exc, "code", None)
                if status == 429 and attempt < RETRIES:
                    sleep(RETRY_PAUSE * (attempt + 1))
                    continue
                tf[tag] = {"error": type(exc).__name__ + (f" {status}" if status else ""),
                           "status": status}
                break
    splits = [] if code.endswith((".CC", ".FOREX", ".INDX")) else eodhd_history.in_force(
        eodhd_history._SPLITS.get(code, []), today or datetime.date.today())
    return tf, splits


def build(*, key, today=None, path=REGISTRY, workers=4, table=None, fetch=None):
    """Mesure toute la table et écrit le registre ; rend le document."""
    today = today or datetime.date.today()
    fetch = fetch or (lambda code, divisor: fetch_series(code, divisor, key=key, today=today))

    def one(item):
        conid, symbol, code, divisor, named = item
        tf, splits = fetch(code, divisor)
        verdict = judge(tf, splits, named=named, today=today)
        return conid, {"symbol": symbol, "eodhd": code, **verdict}

    with concurrent.futures.ThreadPoolExecutor(workers) as pool:
        series = dict(pool.map(one, targets(table)))
    document = {
        "_meta": {
            "checked_on": today.isoformat(),
            "about": "Verdicts des gardes EODHD, série EODHD seule (scripts/eodhd_guards.py).",
            "guards": list(GUARDS),
        },
        "series": dict(sorted(series.items())),
    }
    jsonio.write(path, document)
    return document


def load(path=REGISTRY):
    """Le registre, ou None s'il manque : une absence de mesure n'est pas « rien »."""
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def flagged(path=REGISTRY):
    """Projection pour l'interface : séries écartées, classées par garde."""
    document = load(path)
    if document is None:
        return None
    series = document.get("series") or {}
    items = []
    unmeasured = 0
    for conid, entry in series.items():
        if entry.get("ok") is None:
            unmeasured += 1
            continue
        if entry.get("ok"):
            continue
        guards = [item["guard"] for item in entry.get("flags") or []]
        items.append({
            "conid": conid, "symbol": entry.get("symbol"), "eodhd": entry.get("eodhd"),
            "guard": min(guards, key=GUARDS.index) if guards else "unavailable",
            "guards": guards,
            "detail": "; ".join(item["detail"] for item in entry.get("flags") or []),
        })
    items.sort(key=lambda item: (GUARDS.index(item["guard"]), item["symbol"] or ""))
    return {"checked_on": (document.get("_meta") or {}).get("checked_on"),
            "measured": len(series) - unmeasured, "unmeasured": unmeasured, "items": items}


def main(argv=None):
    parser = argparse.ArgumentParser(description="Gardes EODHD, série seule (lecture seule du cache).")
    parser.add_argument("--symbol", help="code EODHD à juger, par exemple BRTX.US")
    parser.add_argument("--build", action="store_true",
                        help="mesure toute la table d'identité et écrit le registre du livre")
    args = parser.parse_args(argv)
    key = eodhd_history.api_key()
    if not key:
        print(eodhd_history.available()[1], file=sys.stderr)
        return 2
    if args.symbol:
        tf, splits = fetch_series(args.symbol, key=key)
        print(json.dumps(judge(tf, splits), ensure_ascii=False, indent=2))
        return 0
    if args.build:
        document = build(key=key)
        verdicts = [entry["ok"] for entry in document["series"].values()]
        print(f"{len(verdicts)} séries, {verdicts.count(False)} écartées, "
              f"{verdicts.count(None)} non mesurées — {REGISTRY}")
        return 0
    parser.print_help()
    return 1


if __name__ == "__main__":
    sys.exit(main())
