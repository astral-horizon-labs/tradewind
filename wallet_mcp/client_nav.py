"""La valeur du livre d'un client dans le temps : NAV quotidienne, ligne sans flux, creux.

POURQUOI (2026-11-07, décision du propriétaire : « tous les tools possibles »). La
baisse du livre depuis son sommet est la seule jauge de peur qui concerne le client
directement ; elle exige l'historique de la valeur du compte, absent du rapport de
positions. Deux requêtes Flex FACULTATIVES la donnent :
    query_id_nav     Net Asset Value (NAV) in Base, Breakout by Day, Last 365 Days
    query_id_cashtx  Cash Transactions, Deposits & Withdrawals, Last 365 Days

UNE SEULE LOI. La série se réduit par `book.nav_series` (la NAV par compte, les flux
externes filtrés par leur `Type`, la ligne sans flux en convention début de journée),
et les creux par `_drawdowns`, comme pour le propriétaire. Chaque tirage se garde
sous un nom daté : un an de Flex à la fois, mais l'historique s'allonge à chaque
tirage, et le plus récent l'emporte sur une date commune.
"""
from __future__ import annotations

import datetime
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
for folder in (ROOT / "scripts", pathlib.Path(__file__).resolve().parent):
    if str(folder) not in sys.path:
        sys.path.insert(0, str(folder))

import _drawdowns  # noqa: E402  # type: ignore[import-not-found]
import atomic_file  # noqa: E402  # type: ignore[import-not-found]
import book  # noqa: E402  # type: ignore[import-not-found]
import client_book  # noqa: E402

MAX_AGE_S = 12 * 3600
STAMP_FILE = "nav-fetched.json"
EPISODE_MIN_PCT = 5.0
SETUP = ("NAV history needs two optional Flex queries: \"Net Asset Value (NAV) in Base\" "
         "(Breakout by Day, Last 365 Days, columns ClientAccountID, ReportDate, Total) and "
         "\"Cash Transactions\" (Deposits & Withdrawals only, Last 365 Days, columns "
         "ClientAccountID, Date/Time, Amount, FXRateToBase, Type, Description); then run "
         "`python3 wallet_mcp/install_client.py --query-id-nav ID --query-id-cashtx ID`")


def flex_dir() -> pathlib.Path:
    return client_book.state_dir() / "flex"


def refresh(config: dict, fetcher, now: datetime.datetime, *, force: bool = False) -> str | None:
    """Tire les deux rapports s'ils ont plus de `MAX_AGE_S` ; rend l'erreur d'un tirage raté."""
    folder = flex_dir()
    stamp = client_book.read_stamp_file(client_book.state_dir() / STAMP_FILE)
    age = client_book.cache_age_s(stamp, now)
    if not force and age is not None and age <= MAX_AGE_S and any(folder.glob("navdaily-*.csv")):
        return None
    day = now.date().isoformat()
    errors = []
    for key, prefix in (("query_id_nav", "navdaily"), ("query_id_cashtx", "cashtx")):
        if not config.get(key):
            continue
        text, error = fetcher(config["token"], config[key])
        if error:
            errors.append(f"{prefix}: {client_book.english(error)}")
            continue
        folder.mkdir(parents=True, exist_ok=True)
        atomic_file.write_text(folder / f"{prefix}-{day}.csv", text)
    if not errors:
        atomic_file.write_text(client_book.state_dir() / STAMP_FILE,
                               json.dumps({"fetched_at": now.isoformat(timespec="seconds")}))
    return "; ".join(errors) or None


def series(fetcher=None, *, now: datetime.datetime | None = None, force: bool = False) -> dict:
    """`{"series": …, "notes": […]}` ou `{"error": …}`."""
    now = now or client_book.now_utc()
    config, error = client_book.read_config()
    if error:
        return {"error": error}
    if not config.get("query_id_nav"):
        return {"error": SETUP}
    stale = refresh(config, fetcher or client_book.default_fetcher, now, force=force)
    if not any(flex_dir().glob("navdaily-*.csv")):
        return {"error": f"no NAV report yet: {stale or 'never fetched'}"}
    notes = [f"today's NAV fetch failed, keeping the reports already fetched: {stale}"] if stale else []
    if not config.get("query_id_cashtx"):
        notes.append("no Cash Transactions query: deposits and withdrawals count as gains or "
                     "losses in the line without flows")
    return {"series": book._nav_series_build(flex_dir()), "notes": notes}


def nav_history(fetcher=None, *, now: datetime.datetime | None = None, refresh_now: bool = False) -> dict:
    """La NAV en fins de mois, le sommet de la ligne sans flux, chaque apport et retrait."""
    found = series(fetcher, now=now, force=refresh_now)
    if "error" in found:
        return found
    data = found["series"]
    dates, nav, twr, flows = data["dates"], data["nav"], data["twr"], data["flows"]
    month_ends = [{"date": day, "nav": round(nav[day], 2), "growth_index": round(twr[day] / twr[dates[0]] * 100, 2)}
                  for index, day in enumerate(dates)
                  if index + 1 == len(dates) or dates[index + 1][:7] != day[:7]]
    peak = max(dates, key=twr.__getitem__)
    return {"first_date": dates[0], "last_date": dates[-1], "nav_last": round(nav[dates[-1]], 2),
            "growth_index_peak": {"date": peak, "value": round(twr[peak] / twr[dates[0]] * 100, 2)},
            "net_flows": round(sum(flows.values()), 2),
            "flows": [{"date": day, "amount": round(amount, 2)} for day, amount in sorted(flows.items())],
            "month_ends": month_ends,
            "legend": ("nav includes deposits and withdrawals; growth_index (base 100 on the first "
                       "day) excludes them: it is what the first day's capital became"),
            "notes": found["notes"]}


def drawdowns(fetcher=None, *, now: datetime.datetime | None = None) -> dict:
    """La baisse depuis le sommet de la ligne sans flux, et les creux passés d'au moins 5 %."""
    found = series(fetcher, now=now)
    if "error" in found:
        return found
    data = found["series"]
    dates = data["dates"]
    values = [data["twr"][day] for day in dates]
    current = _drawdowns.current(values, dates)
    episodes = _drawdowns.episodes(values, dates, EPISODE_MIN_PCT)
    depths = sorted(episode["depth_pct"] for episode in episodes)
    median = depths[len(depths) // 2] if depths else None
    worst_pct, worst_on = _drawdowns.worst(values, dates)
    return {"first_date": dates[0], "last_date": dates[-1],
            "current": {"pct": round(current["pct"], 2), "peak_on": current["peak_on"],
                        "last_on": current["last_on"]},
            "worst": {"pct": round(worst_pct, 2), "on": worst_on},
            "episodes_min_pct": EPISODE_MIN_PCT,
            "episodes": [{key: (round(value, 2) if isinstance(value, float) else value)
                          for key, value in episode.items()} for episode in episodes],
            "median_depth_pct": round(median, 2) if median is not None else None,
            "reading": ("measured without deposits and withdrawals; past episodes are context, "
                        "not a threshold; the history starts at first_date (IBKR serves one "
                        "year at a time), so a peak before it is not seen, and the history "
                        "lengthens with every daily fetch"),
            "notes": found["notes"]}
