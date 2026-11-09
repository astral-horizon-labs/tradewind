"""Le marché d'un client : tout titre suivi, sa force relative, ses paniers.

POURQUOI (2026-11-07, décision du propriétaire : « améliore le mcp avec tous les tools
possibles »). La méthode juge une ligne d'abord contre son marché : un titre qui monte
moins que son panier ou que le S&P 500 ne porte pas le pari, même en hausse. Le MCP
client n'avait que le graphique des lignes DÉTENUES ; il lui manquait le titre qu'on
étudie avant d'acheter, la force relative et le panier.

LES SOURCES. Rien du compte : un symbole se résout en conid par le rapport Flex
(ligne détenue), puis par la graine de marché livrée (`ratio-universe-method.json`,
383 instruments), puis par les paniers livrés (`baskets.json`, 83 paniers). Les
séries viennent de notre serveur de prix, comme le reste. Le serveur limite chaque
clé en requêtes par minute : un panier se calcule sur ses membres déjà servis, et un
membre absent du serveur est nommé, jamais deviné.

Toutes les mesures portent sur les clôtures hebdomadaires RÉGLÉES, alignées par
semaine : deux séries ne se comparent que sur leurs semaines communes.
"""
from __future__ import annotations

import datetime
import json
import os
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
for folder in (ROOT / "scripts", pathlib.Path(__file__).resolve().parent):
    if str(folder) not in sys.path:
        sys.path.insert(0, str(folder))

import atomic_file  # noqa: E402  # type: ignore[import-not-found]
import client_book  # noqa: E402
import client_messages  # noqa: E402
import client_prices  # noqa: E402
import data_root  # noqa: E402  # type: ignore[import-not-found]
import prices_server  # noqa: E402  # type: ignore[import-not-found]
from market_ranking import change_pct, equal_weight  # noqa: E402,F401  # type: ignore[import-not-found]

BASKETS_FILE = ROOT / "references" / "baskets.json"
BENCHMARK = "SPY"
WINDOWS = (4, 13, 26, 52)
SMA_WEEKS = 10
#: Au-delà, un panier se lit sur ses premiers membres : le serveur plafonne chaque clé.
MAX_MEMBERS = 40
RANKING_FILE = "market-baskets.json"
#: Le classement se republie après chaque collecte : six heures suffisent.
RANKING_MAX_AGE_S = 6 * 3600


def seed() -> dict:
    try:
        return json.loads(data_root.universe_seed_file().read_text(encoding="utf-8"))["instruments"]
    except (OSError, ValueError, KeyError):
        return {}


def baskets() -> dict[str, list[dict]]:
    try:
        return json.loads(BASKETS_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def baskets_of(symbol: str) -> list[str]:
    wanted = symbol.strip().upper()
    return [name for name, members in baskets().items()
            if any(member.get("symbol", "").upper() == wanted for member in members)]


def resolve(symbol: str, held: list[dict] | None = None) -> dict | None:
    """`{"symbol", "conid", "source", "name"?}` d'un symbole connu, ou None."""
    wanted = symbol.strip().upper()
    for position in held or []:
        if position["contract_description"].split(" @")[0].upper() == wanted:
            return {"symbol": wanted, "conid": position["contract_id"], "source": "holding",
                    "currency": position.get("currency")}
    found = seed().get(wanted)
    if found and found.get("conid"):
        return {"symbol": wanted, "conid": found["conid"], "source": "market universe"}
    for name, members in baskets().items():
        for member in members:
            if member.get("symbol", "").upper() == wanted and member.get("conid"):
                return {"symbol": wanted, "conid": member["conid"], "source": f"basket {name}",
                        "name": member.get("name")}
    return None


def held_positions(now: datetime.datetime) -> list[dict]:
    """Les lignes du rapport Flex, ou rien si le livre est illisible : le marché s'en passe."""
    book = client_book.load_book(now=now)
    return [] if "error" in book else book["snapshot"]["positions"]


def getter_or_error():
    return client_prices.server_getter(client_book.prices_config())


def weekly_closes(conid: int, getter, now: datetime.datetime) -> tuple[dict[str, float], list[dict], str | None]:
    """({semaine: clôture}, bougies réglées, erreur) d'un conid, sur toute la série servie."""
    found = client_prices.series(conid, client_book.state_dir() / "series", getter, now)
    if "error" in found:
        return {}, [], found["error"]
    weeks = client_prices.settled_weeks(found["series"], now.date(), weeks=10_000)
    return {week["week"]: week["c"] for week in weeks}, weeks, None


def ratio_bars(numerator: dict[str, float], denominator: dict[str, float], weeks: int) -> list[dict]:
    """Le ratio semaine par semaine, en bougies d'une clôture à l'autre, pour le dessin."""
    common = sorted(set(numerator) & set(denominator))[-weeks - 1:]
    bars, previous = [], None
    for week in common:
        value = numerator[week] / denominator[week]
        start = previous if previous is not None else value
        bars.append({"week": week, "o": start, "c": value, "h": max(start, value), "l": min(start, value)})
        previous = value
    return bars[1:] if len(bars) > 1 else bars


def benchmark_closes(against: str, target: dict, held: list[dict], getter,
                     now: datetime.datetime) -> tuple[dict[str, float], str, list[str], str | None]:
    """(clôtures du repère, son nom, notes, erreur). `against` : un symbole, ou « basket »."""
    if against.strip().lower() != "basket":
        bench = resolve(against, held)
        if bench is None:
            return {}, against, [], f"{against.upper()} is unknown: neither a holding, nor in the market universe, nor in a basket"
        closes, _, error = weekly_closes(bench["conid"], getter, now)
        return closes, bench["symbol"], [], error
    names = baskets_of(target["symbol"])
    if not names:
        return {}, "basket", [], f"{target['symbol']} belongs to no basket: compare it with a symbol instead (SPY, QQQ, XLV…)"
    return basket_index(names[0], getter, now, exclude=target["symbol"])


def basket_index(name: str, getter, now: datetime.datetime, *, exclude: str | None = None
                 ) -> tuple[dict[str, float], str, list[str], str | None]:
    members = [member for member in baskets().get(name, []) if member.get("conid")
               and member.get("symbol", "").upper() != (exclude or "").upper()][:MAX_MEMBERS]
    series, missing = [], []
    for member in members:
        closes, _, error = weekly_closes(member["conid"], getter, now)
        (missing.append(member["symbol"]) if error or not closes else series.append(closes))
    notes = [f"members without a series on our server, left out: {', '.join(missing)}"] if missing else []
    if not series:
        return {}, name, notes, f"no member of the basket {name} has a series on our server"
    return equal_weight(series), f"basket {name} (equal weight, {len(series)} members)", notes, None


def relative_strength(symbol: str, against: str = BENCHMARK, getter=None, *,
                      now: datetime.datetime | None = None) -> dict:
    """Le titre face à un repère : ratio hebdomadaire dessiné, écart sur 4 à 52 semaines,
    ratio face à sa moyenne de dix semaines et sens des dernières semaines."""
    import png_chart

    now = now or client_book.now_utc()
    held = held_positions(now)
    target = resolve(symbol, held)
    if target is None:
        return {"error": f"{symbol.upper()} is unknown: neither a holding, nor in the market universe, nor in a basket"}
    if getter is None:
        getter, error = getter_or_error()
        if error:
            return {"error": error}
    closes, _, error = weekly_closes(target["conid"], getter, now)
    if error:
        return {"error": f"{target['symbol']}: {error}"}
    bench, bench_name, notes, error = benchmark_closes(against, target, held, getter, now)
    if error:
        return {"error": error}
    common = sorted(set(closes) & set(bench))
    if len(common) < SMA_WEEKS + 2:
        return {"error": f"not enough common weekly history between {target['symbol']} and {bench_name}"}
    own = [closes[week] for week in common]
    other = [bench[week] for week in common]
    ratio = [a / b for a, b in zip(own, other)]
    sma = sum(ratio[-SMA_WEEKS:]) / SMA_WEEKS
    png, grid = png_chart.weekly_png(ratio_bars(closes, bench, client_prices.WEEKS))
    windows = {}
    for weeks in WINDOWS:
        mine, theirs = change_pct(own, weeks), change_pct(other, weeks)
        windows[f"{weeks}w"] = {"symbol_pct": mine, "benchmark_pct": theirs,
                                "spread_pts": round(mine - theirs, 2) if None not in (mine, theirs) else None}
    recent = [round(value, 6) for value in ratio[-5:]]
    trend = ("improving" if recent[-1] > recent[0] else "deteriorating" if recent[-1] < recent[0] else "flat")
    return {
        "png": png,
        "symbol": target["symbol"],
        "benchmark": bench_name,
        "last_settled_week": common[-1],
        "ratio_vs_sma10": round(ratio[-1] / sma, 4),
        "above_sma10": ratio[-1] > sma,
        "last_five_ratios": recent,
        "trend_5w": trend,
        "windows": windows,
        "grid_levels_top_down": grid,
        "legend": ("each candle is one settled week of the ratio symbol ÷ benchmark, green when "
                   "the symbol beat the benchmark that week, red when it lagged; log scale; a rising "
                   "line means the symbol leads"),
        "notes": notes,
    }


def basket(query: str, getter=None, *, now: datetime.datetime | None = None) -> dict:
    """Un panier, nommé ou désigné par l'un de ses membres : ses membres classés par force
    sur 13 semaines, et le panier équipondéré face au S&P 500."""
    now = now or client_book.now_utc()
    every = baskets()
    wanted = query.strip()
    name = next((key for key in every if key.upper() == wanted.upper()), None)
    memberships = [] if name else baskets_of(wanted)
    if name is None and not memberships:
        return {"error": f"{wanted} is neither a basket nor a member of one",
                "baskets": sorted(every)}
    name = name or memberships[0]
    if getter is None:
        getter, error = getter_or_error()
        if error:
            return {"error": error}
    spy = resolve(BENCHMARK)
    spy_closes, _, error = weekly_closes(spy["conid"], getter, now) if spy else ({}, [], "SPY unknown")
    if error:
        return {"error": f"{BENCHMARK}: {error}"}
    spy_list = [spy_closes[week] for week in sorted(spy_closes)]
    rows, series, missing = [], [], []
    for member in [m for m in every[name] if m.get("conid")][:MAX_MEMBERS]:
        closes, _, error = weekly_closes(member["conid"], getter, now)
        if error or not closes:
            missing.append(member["symbol"])
            continue
        series.append(closes)
        values = [closes[week] for week in sorted(closes)]
        rows.append({"symbol": member["symbol"], "name": member.get("name"),
                     "last_settled_week": max(closes),
                     **{f"change_{weeks}w_pct": change_pct(values, weeks) for weeks in (4, 13, 26)}})
    rows.sort(key=lambda row: row["change_13w_pct"] if row["change_13w_pct"] is not None else -1e9,
              reverse=True)
    index = equal_weight(series)
    index_list = [index[week] for week in sorted(index)]
    summary = {f"{weeks}w": {"basket_pct": change_pct(index_list, weeks),
                             "spy_pct": change_pct(spy_list, weeks)} for weeks in (4, 13, 26, 52)}
    for window in summary.values():
        mine, theirs = window["basket_pct"], window["spy_pct"]
        window["spread_pts"] = round(mine - theirs, 2) if None not in (mine, theirs) else None
    return {"basket": name, "other_baskets_of_symbol": memberships[1:],
            "basket_vs_spy": summary, "members_by_13w_strength": rows,
            "notes": [f"members without a series on our server, left out: {', '.join(missing)}"] if missing else [],
            "next": "relative_strength(symbol, against=\"basket\") draws a member against this basket"}


def ranking(client=None, *, now: datetime.datetime | None = None) -> dict:
    """Le classement de tous les paniers face au S&P 500, calculé par le poste qui collecte
    (`scripts/market_ranking.py`) et lu en une requête sur notre serveur ; gardé six heures."""
    now = now or client_book.now_utc()
    path = client_book.state_dir() / RANKING_FILE
    fresh = path.exists() and now.timestamp() - path.stat().st_mtime < RANKING_MAX_AGE_S
    stale = None
    missing = False
    if not fresh:
        if client is None:
            client, error = client_prices.server_client(client_book.prices_config())
            if error:
                return {"error": error}
        try:
            payload = client.get_market()
            json.loads(payload)
            path.parent.mkdir(parents=True, exist_ok=True)
            atomic_file.write_text(path, payload.decode("utf-8"))
            os.utime(path, (now.timestamp(), now.timestamp()))
        except prices_server.ServerError as error:
            missing = error.status == 404
            stale = client_messages.server_error(error)
        except (ValueError, UnicodeDecodeError):
            stale = "the server returned an unreadable ranking"
    if not path.exists():
        if missing:
            return {"error": "no basket ranking on our server yet"}
        return {"error": f"basket ranking unavailable: {stale}"}
    found = json.loads(path.read_text(encoding="utf-8"))
    if stale:
        found["notes"] = [f"today's fetch failed, showing the copy fetched earlier: {stale}"]
    found["next"] = ("basket(name) ranks one basket's members; relative_strength(symbol, "
                     "against=\"basket\") draws a member against its basket")
    return found
