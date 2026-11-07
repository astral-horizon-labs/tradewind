#!/usr/bin/env python3
"""Adaptateur EODHD : historique 1D/1W/1M au format interne, derrière `fetch_hook`."""
from __future__ import annotations

import argparse
import collections
import datetime
import json
import os
import pathlib
import sys
import threading
import urllib.error
import urllib.parse
import urllib.request

import bar_calendar
import market_identity

API = "https://eodhd.com/api"
KEY_PATH = pathlib.Path(os.path.expanduser("~/.config/ibkr-wallet/eodhd-api-key"))
DEMO_KEY = "demo"
PROVIDER = "eodhd"

PERIOD_BY_BAR = {"1d": "d", "1w": "w", "1m": "m"}
TAG_BY_BAR = {"1d": "1D", "1w": "1W", "1m": "1M"}


def key_problem(path=KEY_PATH):
    """Motif d'indisponibilité de la clé, ou None si elle est utilisable."""
    path = pathlib.Path(path)
    try:
        mode = path.stat().st_mode & 0o777
    except OSError:
        return f"clé EODHD absente ({path}) : adaptateur indisponible"
    if mode & 0o077:
        return (f"clé EODHD refusée ({path}) : droits {mode:o}, "
                f"lancer `chmod 600 {path}`")
    try:
        if not path.read_text(encoding="utf-8").strip():
            return f"clé EODHD vide ({path}) : adaptateur indisponible"
    except OSError as exc:
        return f"clé EODHD illisible ({path}) : {exc}"
    return None


def api_key(path=KEY_PATH):
    """La clé déposée, ou None. Jamais lue ailleurs, jamais journalisée."""
    if key_problem(path):
        return None
    return pathlib.Path(path).read_text(encoding="utf-8").strip()


def available(path=KEY_PATH):
    """(disponible, motif) — le motif dit quoi faire, pas seulement quoi manque."""
    problem = key_problem(path)
    return problem is None, problem


def normalize_bar(bar):
    bar = str(bar).lower()
    if bar not in PERIOD_BY_BAR:
        raise ValueError(f"granularité EODHD non prise en charge : {bar}")
    return bar


def aligned_start(bar, period, today=None):
    """Début de période le plus proche AVANT `today - period` : `from` coupe les barres."""
    today = today or datetime.date.today()
    unit, count = period[-1], int(period[:-1])
    if unit == "y":
        start = datetime.date(today.year - count, today.month, 1)
    elif unit == "m":
        month = today.year * 12 + today.month - 1 - count
        start = datetime.date(month // 12, month % 12 + 1, 1)
    elif unit == "d":
        start = today - datetime.timedelta(days=count)
    else:
        raise ValueError(f"période EODHD invalide : {period}")
    if bar == "1w":
        start -= datetime.timedelta(days=start.weekday())
    return start




CALLS: collections.Counter = collections.Counter()
_CALLS_LOCK = threading.Lock()


_quota_closed_on: str | None = None
QUOTA_REASON = "quota EODHD du jour épuisé (HTTP 402) : plus aucun appel avant 00:00 UTC"


def _utc_today():
    return datetime.datetime.now(datetime.timezone.utc).date().isoformat()


def request_json(path, params, key, opener=None, timeout=30):
    """GET sur l'API ; lève `urllib.error.HTTPError` tel quel."""
    endpoint = path.split("/", 1)[0]
    if quota_exhausted():
        raise urllib.error.HTTPError(f"{API}/{path}", 402, QUOTA_REASON, None, None)
    query = urllib.parse.urlencode({**params, "fmt": "json", "api_token": key})
    url = f"{API}/{path}?{query}"
    opener = opener or urllib.request.urlopen
    with _CALLS_LOCK:
        CALLS[endpoint] += 1
    try:
        with opener(url, timeout=timeout) as response:
            return json.load(response)
    except urllib.error.HTTPError as exc:
        exc.close()
        if exc.code == 402:
            _close_for_quota()

            raise urllib.error.HTTPError(f"{API}/{path}", 402, QUOTA_REASON, None, None) from None
        raise


def _close_for_quota():
    global _quota_closed_on
    _quota_closed_on = _utc_today()


def quota_exhausted():
    """Le motif de fermeture si un 402 a été reçu ce jour UTC, sinon None."""
    global _quota_closed_on
    if _quota_closed_on and _quota_closed_on != _utc_today():
        _quota_closed_on = None
    return QUOTA_REASON if _quota_closed_on else None


def parse_splits(rows):
    """[(date ISO, facteur)] — facteur = actions après / avant (4 pour 4:1, 0,1 pour 1:10)."""
    found = []
    for row in rows or []:
        after, _, before = str(row.get("split", "")).partition("/")
        try:
            factor = float(after) / float(before)
        except (ValueError, ZeroDivisionError):
            continue
        if factor > 0 and factor != 1:
            found.append((row["date"], factor))
    return sorted(found)


def in_force(splits, today):
    """Les splits déjà entrés en vigueur à `today`."""
    day = str(today)[:10]
    return [split for split in splits if split[0] <= day]


def factor_after(day, splits):
    """Diviseur des prix d'un jour : produit des splits entrés en vigueur APRÈS lui."""
    divisor = 1.0
    for effective, factor in splits:
        if day < effective:
            divisor *= factor
    return divisor


def _scaled(row, divisor):
    return {key: row[key] / divisor if row.get(key) is not None else None
            for key in ("open", "high", "low", "close")}


def adjust_for_splits(rows, splits, bar, daily=None):
    """OHLC ajusté des seuls splits ; une barre qui en contient un est reconstruite."""
    tag = TAG_BY_BAR[bar]
    adjusted = []
    for row in rows:
        start = row["date"]
        end = bar_calendar.period_end(start, tag).isoformat()
        inside = [effective for effective, _ in splits if start < effective <= end]
        if not inside or tag == "1D":
            adjusted.append({**row, **_scaled(row, factor_after(start, splits))})
            continue
        if daily is None:
            continue
        days = [{**day, **_scaled(day, factor_after(day["date"], splits))}
                for day in daily(start, end) if day.get("close")]
        if not days:
            continue
        adjusted.append({
            "date": start, "open": days[0]["open"], "close": days[-1]["close"],
            "high": max(day["high"] for day in days),
            "low": min(day["low"] for day in days),
            "volume": sum(day.get("volume") or 0 for day in days),
            "rebuilt_from_daily": True,
        })
    return adjusted


def drop_partial(rows, bar, today=None, week_ends_sunday=False):
    """(réglées, partielles) : une barre dont la fin calendaire n'est pas passée sort."""
    today = today or datetime.date.today()
    tag = TAG_BY_BAR[bar]
    settled, partial = [], []
    for row in rows:
        end = bar_calendar.period_end(row["date"], tag, week_ends_sunday)
        (partial if end >= today else settled).append(row)
    return settled, partial


def to_internal(rows, divisor=1):
    """Barres EODHD -> format de `backfill_cache.fetch`, provenance comprise."""
    bars = []
    for row in rows:
        day = datetime.datetime.strptime(row["date"], "%Y-%m-%d").replace(
            tzinfo=datetime.timezone.utc)
        bar = {"t": int(day.timestamp() * 1000), "src": PROVIDER}
        for short, field in (("o", "open"), ("h", "high"), ("l", "low"), ("c", "close")):
            value = row.get(field)
            bar[short] = value / divisor if value is not None else None
        bar["v"] = row.get("volume")
        if row.get("rebuilt_from_daily"):
            bar["rebuilt_from_daily"] = True
        bars.append(bar)
    return bars




_SPLITS = {}


def splits_of(code, key, opener=None):
    if code not in _SPLITS:
        _SPLITS[code] = parse_splits(
            request_json(f"splits/{code}", {"from": "1900-01-01"}, key, opener))
    return _SPLITS[code]


def fetch_symbol(code, bar, period, *, key, metadata=None, divisor=1, opener=None,
                 today=None):
    """Barres réglées et ajustées d'un code EODHD. Lève sur erreur réseau ou HTTP."""
    bar = normalize_bar(bar)
    today = today or datetime.date.today()
    metadata = {} if metadata is None else metadata
    start = aligned_start(bar, period, today)
    rows = request_json(f"eod/{code}", {"period": PERIOD_BY_BAR[bar],
                                         "from": start.isoformat()}, key, opener)
    metadata["bars_served"] = len(rows)
    crypto = code.endswith(".CC")
    splits = ([] if crypto or code.endswith((".FOREX", ".INDX"))
              else in_force(splits_of(code, key, opener), today))
    if splits:
        metadata["splits"] = [f"{effective} x{factor:g}" for effective, factor in splits]

    def daily(first, last):
        return request_json(f"eod/{code}", {"period": "d", "from": first, "to": last},
                            key, opener)

    rows = adjust_for_splits(rows, splits, bar, daily)
    settled, partial = drop_partial(rows, bar, today, week_ends_sunday=crypto)
    if partial:
        metadata["dropped_partial"] = [row["date"] for row in partial]
    return to_internal(settled, divisor)


def period_sessions(conid, bar, date, *, key, table=None, opener=None):
    """[(séance, clôture)] de la période de `date`, ajustées des splits et du diviseur."""
    row = market_identity.symbol_for(conid, PROVIDER, table=table)
    if not row:
        return []
    code, divisor = row["symbol"], row.get("divisor", 1)
    day = datetime.date.fromisoformat(date[:10])
    span = 10 if bar.upper() == "1W" else 40
    rows = request_json(f"eod/{code}", {
        "from": (day - datetime.timedelta(days=span)).isoformat(),
        "to": (day + datetime.timedelta(days=span)).isoformat(),
    }, key, opener)
    splits = in_force(splits_of(code, key, opener), datetime.date.today())
    period = bar_calendar.bar_period(date[:10], bar.upper())
    return [(r["date"], r["close"] / divisor / factor_after(r["date"], splits))
            for r in rows or []
            if r.get("close") and bar_calendar.bar_period(r["date"], bar.upper()) == period]


def fetch(conid, bar, period, metadata=None, *, table=None, key=None, opener=None,
          today=None, key_path=KEY_PATH):
    """Même contrat que `backfill_cache.fetch` : barres ou liste vide, motif dans `metadata`."""
    metadata = {} if metadata is None else metadata
    metadata["provider"] = PROVIDER
    key = key or api_key(key_path)
    if not key:
        metadata["error"] = available(key_path)[1]
        return []
    row = market_identity.symbol_for(conid, PROVIDER, on=today, table=table)
    if not row:
        entry = (market_identity.load() if table is None else table).get(str(conid)) or {}
        metadata["error"] = ("identité EODHD non établie : "
                             + (entry.get("eodhd_unresolved") or "conid absent de la table"))
        return []
    metadata["symbol"] = row["symbol"]
    try:
        return fetch_symbol(row["symbol"], bar, period, key=key, metadata=metadata,
                            divisor=row.get("divisor", 1), opener=opener, today=today)
    except urllib.error.HTTPError as exc:
        metadata["http_status"] = exc.code
        metadata["error"] = f"HTTP {exc.code} EODHD"
    except Exception as exc:




        metadata["exception"] = f"{type(exc).__name__}: {exc}"
    return []


def main(argv=None):
    parser = argparse.ArgumentParser(description="Historique EODHD au format interne (lecture seule).")
    target = parser.add_mutually_exclusive_group(required=True)
    target.add_argument("--symbol", help="code EODHD (AAPL.US, BTC-USD.CC, EURUSD.FOREX)")
    target.add_argument("--conid", help="conid, résolu par references/market-identity.json")
    parser.add_argument("--bar", default="1M", help="1D, 1W ou 1M")
    parser.add_argument("--period", default="2y", help="profondeur : 15y, 6m, 30d")
    parser.add_argument("--demo", action="store_true", help="clé publique « demo » d'EODHD")
    parser.add_argument("--last", type=int, default=5, help="nombre de barres affichées")
    args = parser.parse_args(argv)
    key = DEMO_KEY if args.demo else api_key()
    if not key:
        print(available()[1])
        return 2
    metadata = {}
    if args.symbol:
        try:
            bars = fetch_symbol(args.symbol, args.bar, args.period, key=key, metadata=metadata)
        except urllib.error.HTTPError as exc:
            metadata["error"] = f"HTTP {exc.code} EODHD"
            bars = []
    else:
        bars = fetch(args.conid, args.bar, args.period, metadata, key=key)
    print(json.dumps(metadata, ensure_ascii=False))
    for bar in bars[-args.last:]:
        day = datetime.datetime.fromtimestamp(bar["t"] / 1000, datetime.timezone.utc).date()
        print(f"{day}  o={bar['o']:.4f} h={bar['h']:.4f} l={bar['l']:.4f} c={bar['c']:.4f}"
              + ("  (reconstruite depuis le quotidien)" if bar.get("rebuilt_from_daily") else ""))
    print(f"{len(bars)} barre(s) réglée(s)")
    return 0 if bars else 1


if __name__ == "__main__":
    sys.exit(main())
