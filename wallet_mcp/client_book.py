"""Le livre d'un investisseur CLIENT, lu par son propre Flex — sans backend.

POURQUOI (2026-11-07, décision du propriétaire). La première cible commerciale est
l'investisseur technique qui travaille dans Claude Code ou Codex
(`distribution-architecture.md` du livre, option B : MCP local avec le skill). Le
serveur `server.py` interroge le backend du propriétaire sur `:8000` et ne sert donc
que SON livre. Ce module lit le compte du client lui-même, avec le jeton Flex que le
client crée dans SON portail IBKR, et en tire le livre au coût. Rien ne quitte sa
machine : le rapport est mis en cache sous son répertoire d'état, et nulle part ailleurs.

Configuration, un fichier JSON hors de tout dépôt :
    ~/.config/wallet/client.json   (ou WALLET_CLIENT_CONFIG)
    {"token": "…", "query_id": "…",            rapport LOT : positions et coûts
     "query_id_cash": "…",                      facultatif : Cash Report, donc le NAV
     "base_currency": "USD",                    facultatif si le rapport la révèle
     "prices_url": "…", "prices_key_file": "…"} notre serveur de prix (`client_prices.py`)

POURQUOI UN CACHE. Un rapport Flex se génère en 5 à 30 s, et il ne change qu'une fois
par jour (batch nocturne d'IBKR) : on ne le retire qu'au-delà de `MAX_AGE_S`. Un
tirage qui échoue rend le dernier rapport gardé, AVEC l'erreur et sa date : une
donnée périmée se dit périmée, elle ne passe jamais pour fraîche.

Erreurs comme valeurs : chaque fonction publique rend un dict, `{"error": …}` en cas
d'échec. Le jeton ne sort jamais, ni dans un message ni dans une réponse.
"""
from __future__ import annotations

import datetime
import json
import os
import pathlib
import sys
from typing import Callable

ROOT = pathlib.Path(__file__).resolve().parent.parent
# `flex_snapshot` vit dans le backend du dépôt, et à côté de ce fichier dans le paquet
# distribué (`build_skill_package.CLIENT_COPIES`) : les deux chemins sont posés.
for folder in (ROOT / "scripts", ROOT / "dashboard" / "backend", pathlib.Path(__file__).resolve().parent):
    if str(folder) not in sys.path:
        sys.path.insert(0, str(folder))

import atomic_file  # noqa: E402  # type: ignore[import-not-found]
import flex_snapshot  # noqa: E402  # type: ignore[import-not-found]
import flex_webservice  # noqa: E402  # type: ignore[import-not-found]

import client_messages  # noqa: E402

#: Six heures : le rapport d'IBKR ne bouge qu'une fois par nuit ; plus souvent, on
#: attendrait 30 s pour relire le même fichier.
MAX_AGE_S = 6 * 3600
TOP_LINES = 10
LOTS_FILE = "lots.csv"
CASH_FILE = "cash.csv"
STAMP_FILE = "fetched.json"

Fetcher = Callable[[str, str], tuple[str | None, str | None]]


def config_path() -> pathlib.Path:
    configured = os.environ.get("WALLET_CLIENT_CONFIG")
    return pathlib.Path(configured).expanduser() if configured else (
        pathlib.Path.home() / ".config" / "wallet" / "client.json")


def state_dir() -> pathlib.Path:
    configured = os.environ.get("WALLET_CLIENT_STATE")
    return pathlib.Path(configured).expanduser() if configured else (
        pathlib.Path.home() / ".local" / "state" / "wallet-client")


def read_config() -> tuple[dict | None, str | None]:
    """`(config, erreur)` : le message dit quoi faire, jamais une valeur lue."""
    path = config_path()
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None, (f"{path} is missing: write {{\"token\": …, \"query_id\": …}} into it, the token "
                      "and LOT query created in the IBKR portal (Performance & Reports → Flex Queries)")
    except (json.JSONDecodeError, UnicodeDecodeError, OSError) as error:
        return None, f"{path} is unreadable: {error.__class__.__name__}"
    if not isinstance(raw, dict):
        return None, f"{path} is unreadable: a JSON object is expected"
    config = {key: str(raw.get(key, "")).strip() for key in
              ("token", "query_id", "query_id_cash", "query_id_nav", "query_id_cashtx", "base_currency",
               "prices_url", "prices_key", "prices_key_file")}
    if not config["token"] or not config["query_id"]:
        return None, f"{path} is incomplete: fill in token and query_id"
    return config, None


def prices_config() -> dict:
    """Les réglages du serveur de prix, même sans Flex configuré : le marché s'en passe."""
    try:
        raw = json.loads(config_path().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    if not isinstance(raw, dict):
        return {}
    return {key: str(raw.get(key, "")).strip() for key in ("prices_url", "prices_key", "prices_key_file")}


def now_utc() -> datetime.datetime:
    return datetime.datetime.now(datetime.timezone.utc)


def read_stamp(folder: pathlib.Path) -> dict:
    return read_stamp_file(folder / STAMP_FILE)


def read_stamp_file(path: pathlib.Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return {}


def cache_age_s(stamp: dict, now: datetime.datetime) -> float | None:
    try:
        fetched = datetime.datetime.fromisoformat(stamp["fetched_at"])
    except (KeyError, TypeError, ValueError):
        return None
    return (now - fetched).total_seconds()


def default_fetcher(token: str, query_id: str) -> tuple[str | None, str | None]:
    return flex_webservice.fetch_statement(token, query_id)


def refresh(config: dict, fetcher: Fetcher, *, force: bool = False,
            now: datetime.datetime | None = None) -> dict:
    """Le rapport en cache, retiré d'IBKR s'il a plus de `MAX_AGE_S`.

    Rend `{"lots": texte, "cash": texte|None, "fetched_at": …, "stale_error": …}`
    ou `{"error": …}` quand aucun rapport n'est disponible du tout.
    """
    now = now or now_utc()
    folder = state_dir()
    stamp = read_stamp(folder)
    age = cache_age_s(stamp, now)
    lots_path, cash_path = folder / LOTS_FILE, folder / CASH_FILE
    stale_error = None
    if force or age is None or age > MAX_AGE_S or not lots_path.exists():
        lots, error = fetcher(config["token"], config["query_id"])
        if error:
            stale_error = error
        else:
            atomic_file.write_text(lots_path, lots)
            cash_error = None
            if config.get("query_id_cash"):
                cash, cash_error = fetcher(config["token"], config["query_id_cash"])
                if cash is not None:
                    atomic_file.write_text(cash_path, cash)
            stamp = {"fetched_at": now.isoformat(timespec="seconds"), "cash_error": cash_error}
            atomic_file.write_text(folder / STAMP_FILE, json.dumps(stamp, ensure_ascii=False))
    if not lots_path.exists():
        return {"error": f"no Flex report: {english(stale_error) or 'never fetched'}"}
    cash_text = None
    if config.get("query_id_cash") and cash_path.exists():
        cash_text = cash_path.read_text(encoding="utf-8")
    return {"lots": lots_path.read_text(encoding="utf-8"), "cash": cash_text,
            "fetched_at": stamp.get("fetched_at"), "cash_error": stamp.get("cash_error"),
            "stale_error": stale_error}


#: Les messages de `flex_snapshot`, partagé avec le backend du propriétaire et donc
#: français, rendus en anglais au client de Tradewind (2026-11-07). Remplacement par
#: fragments, du plus long au plus court ; un message neuf non traduit passe tel quel.
SNAPSHOT_ENGLISH = (
    ("reconstruit du Flex sans le rapport cash", "rebuilt from Flex without the cash report"),
    ("ligne(s) au Conid illisible écartée(s)", "row(s) with an unreadable Conid dropped"),
    ("ligne BASE_SUMMARY absente du rapport cash", "BASE_SUMMARY row missing from the cash report"),
    ("aucune ligne SUMMARY dans le rapport Flex", "no SUMMARY row in the Flex report"),
    ("rapport Flex sans position exploitable", "Flex report without a usable position"),
    ("ReportDate ambigu", "ambiguous ReportDate"),
    ("EndingCash illisible", "unreadable EndingCash"),
    ("NAV indisponible", "NAV unavailable"),
    ("illisible", "unreadable"),
    ("(absent)", "(missing)"),
)


def english(text: str | None) -> str | None:
    """Un message de `flex_snapshot` ou du tirage Flex en anglais."""
    for french, words in SNAPSHOT_ENGLISH:
        text = text.replace(french, words) if text else text
    return client_messages.english(text)


def base_currency(config: dict, lots_text: str) -> tuple[str | None, str | None]:
    """La devise de base : déclarée, sinon la seule devise au change de 1 dans le rapport.

    Le rapport LOT ne la nomme pas. Une seule devise à `FXRateToBase == 1` la désigne
    sans ambiguïté ; sinon (aucune ligne dans la devise de base, ou deux devises à
    parité), on la demande plutôt que de la deviner : un libellé faux sur des montants
    justes est l'erreur du 2026-07-18 (« GBP » affiché sur des montants en euros).
    """
    if config.get("base_currency"):
        return config["base_currency"].upper(), None
    import csv
    import io
    at_par = set()
    for row in csv.DictReader(io.StringIO(lots_text)):
        if row.get("LevelOfDetail") == "SUMMARY" and row.get("FXRateToBase") in ("1", "1.0", "1.00"):
            at_par.add(row.get("CurrencyPrimary"))
    if len(at_par) == 1:
        return at_par.pop(), None
    return None, ("the report does not determine the base currency: set "
                  f"\"base_currency\" in {config_path()}")


def load_book(fetcher: Fetcher | None = None, *, force: bool = False,
              now: datetime.datetime | None = None) -> dict:
    """Le snapshot du client (format du backend), avec la fraîcheur du tirage."""
    config, error = read_config()
    if error:
        return {"error": error}
    report = refresh(config, fetcher or default_fetcher, force=force, now=now)
    if "error" in report:
        return report
    base, error = base_currency(config, report["lots"])
    if error:
        return {"error": error}
    snapshot, error = flex_snapshot.build(report["lots"], cash_text=report["cash"], base=base)
    if error:
        return {"error": f"unusable Flex report: {english(error)}"}
    notes = []
    if report["stale_error"]:
        notes.append(f"today's fetch failed, keeping the report from {report['fetched_at']}: "
                     f"{english(report['stale_error'])}")
    if not config.get("query_id_cash"):
        notes.append("no Cash Report query: NAV and cash unavailable")
    elif report.get("cash_error"):
        notes.append(f"cash report failed: {english(report['cash_error'])}")
    return {"snapshot": snapshot, "fetched_at": report["fetched_at"], "notes": notes}


def amount(block: dict | None) -> float | None:
    return block.get("amount") if isinstance(block, dict) else None


def lines(snapshot: dict) -> list[dict]:
    """Chaque ligne en devise de base, avec ses poids au COÛT et à la valeur."""
    rates = snapshot["fx"]["rates"]
    rows = []
    for position in snapshot["positions"]:
        rate = rates.get(position["currency"])
        quantity, average = position["position"], position["average_price"]
        cost = quantity * average * rate if None not in (rate, average) else None
        value = position["market_value"] * rate if None not in (rate, position["market_value"]) else None
        rows.append({"symbol": position["contract_description"], "quantity": quantity,
                     "currency": position["currency"], "asset_class": position["asset_class"],
                     "cost_base": cost, "value_base": value, "market_price": position["market_price"]})
    total_cost = sum(row["cost_base"] for row in rows if row["cost_base"] is not None)
    total_value = sum(row["value_base"] for row in rows if row["value_base"] is not None)
    for row in rows:
        cost, value = row["cost_base"], row["value_base"]
        row["weight_cost_pct"] = round(cost / total_cost * 100, 2) if cost is not None and total_cost else None
        row["weight_value_pct"] = round(value / total_value * 100, 2) if value is not None and total_value else None
        row["pnl_base"] = round(value - cost, 2) if None not in (cost, value) else None
        row["pnl_pct"] = round((value / cost - 1) * 100, 2) if None not in (cost, value) and cost else None
        row["cost_base"] = round(cost, 2) if cost is not None else None
        row["value_base"] = round(value, 2) if value is not None else None
    rows.sort(key=lambda row: row["weight_cost_pct"] or 0, reverse=True)
    return rows


def positions(fetcher: Fetcher | None = None, **options) -> dict:
    book = load_book(fetcher, **options)
    if "error" in book:
        return book
    snapshot = book["snapshot"]
    return {"date": snapshot["date"], "fetched_at": book["fetched_at"],
            "base_currency": snapshot["fx"]["base"], "notes": book["notes"],
            "lines": lines(snapshot)}


def book_summary(fetcher: Fetcher | None = None, **options) -> dict:
    book = load_book(fetcher, **options)
    if "error" in book:
        return book
    snapshot = book["snapshot"]
    rows = lines(snapshot)
    summary = snapshot["summary"]
    total_cost = sum(row["cost_base"] for row in rows if row["cost_base"] is not None)
    return {
        "date": snapshot["date"],
        "fetched_at": book["fetched_at"],
        "source": "flex",
        "base_currency": snapshot["fx"]["base"],
        "net_liquidation": amount(summary.get("net_liquidation")),
        "total_cash_value": amount(summary.get("total_cash_value")),
        "gross_position_value": amount(summary.get("gross_position_value")),
        "total_cost": round(total_cost, 2),
        "line_count": len(rows),
        "top_by_cost": [{key: row[key] for key in ("symbol", "weight_cost_pct", "pnl_pct")}
                        for row in rows[:TOP_LINES]],
        "notes": book["notes"] + ([english(summary["note"])] if summary.get("note") else []),
    }


def setup_status() -> dict:
    """Ce qui est configuré et l'âge du rapport gardé, sans rien tirer ni rien révéler."""
    config, error = read_config()
    stamp = read_stamp(state_dir())
    age = cache_age_s(stamp, now_utc())
    return {
        "config_file": str(config_path()),
        "config_error": error,
        "cash_report": bool(config and config.get("query_id_cash")),
        "nav_history": bool(config and config.get("query_id_nav")),
        "deposits_withdrawals": bool(config and config.get("query_id_cashtx")),
        "base_currency": (config or {}).get("base_currency") or None,
        "state_dir": str(state_dir()),
        "last_fetch": stamp.get("fetched_at"),
        "cache_age_hours": round(age / 3600, 1) if age is not None else None,
    }


def weekly_chart(symbol: str, getter=None, *, now: datetime.datetime | None = None) -> dict:
    """Bougies hebdomadaires réglées d'un titre, sur deux ans, avec le coût moyen s'il est détenu.

    Rend `{"png": octets, …}` ou `{"error": …}`. Une ligne détenue se trouve par son
    symbole dans le rapport Flex ; un titre non détenu (une idée qu'on étudie, un
    membre de panier) par la graine de marché ou les paniers livrés (`client_market`,
    2026-11-07). Sa série vient de notre serveur de prix, par son conid.
    """
    import client_prices
    import png_chart

    now = now or now_utc()
    config, error = read_config()
    if error:
        return {"error": error}
    book = load_book(now=now)
    if "error" in book:
        return book
    wanted = symbol.strip().upper()
    held = [p for p in book["snapshot"]["positions"]
            if p["contract_description"].split(" @")[0].upper() == wanted]
    if held:
        position = held[0]
    else:
        import client_market
        found = client_market.resolve(wanted)
        if found is None:
            return {"error": f"{wanted} is unknown: neither a holding (Flex report of "
                             f"{book['snapshot']['date']}), nor in the market universe, nor in a basket"}
        position = {"contract_id": found["conid"], "currency": None, "average_price": None}
    if getter is None:
        getter, error = client_prices.server_getter(config)
        if error:
            return {"error": error}
    found = client_prices.series(position["contract_id"], state_dir() / "series", getter, now)
    if "error" in found:
        return found
    weeks = client_prices.settled_weeks(found["series"], now.date())
    if len(weeks) < 2:
        return {"error": f"not enough weekly history for {wanted}"}
    cost = position["average_price"]
    import client_plans
    plan_levels = client_plans.chart_levels(wanted, position["contract_id"], getter, now) if held else []
    png, levels = png_chart.weekly_png(weeks, cost, plan_levels)
    closes = [week["c"] for week in weeks]
    last = weeks[-1]
    notes = [f"price server unreachable, keeping the cached series: {found['stale_error']}"] if found["stale_error"] else []
    return {
        "png": png,
        "symbol": wanted,
        "currency": position["currency"],
        "last_settled_week": last["week"],
        "last_close": last["c"],
        "first_week": weeks[0]["week"],
        "high_2y": max(week["h"] for week in weeks),
        "low_2y": min(week["l"] for week in weeks),
        "average_cost": cost,
        "held": bool(held),
        "change_13w_pct": round((closes[-1] / closes[-14] - 1) * 100, 1) if len(closes) > 13 else None,
        "grid_levels_top_down": levels,
        "plan_levels": plan_levels,
        "legend": ("green candles up, red down; blue dashes: the client's average cost; "
                   "solid lines: plan levels (orange exit or trim, green add, grey warning); "
                   "log scale"),
        "notes": notes,
    }
