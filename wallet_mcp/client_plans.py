"""Le plan de chaque ligne d'un client : écrit par son agent, suivi sur nos prix.

POURQUOI (2026-11-07, décision du propriétaire, lot 3 du MCP client). Le plan par
ligne est le cœur de la méthode (« plan the trade, trade the plan ») : entrée,
invalidation, sortie, horizon, écrits AVANT d'en avoir besoin. Sans lui, le MCP
client n'est qu'un lecteur de positions.

UNE SEULE LOI POUR LES DEUX LIVRES. Un plan se valide par `decision_schema`, comme
chez le propriétaire : refusé pour les mêmes raisons, avec le même texte. Un
niveau s'évalue par `tripwires.check_level` et `tripwires.level_px` (seuil fixe,
moyenne mobile, palier à cliquet), sur les clôtures RÉGLÉES de la série que notre
serveur de prix a servie au client. Rien n'est recopié : une correction de la loi
vaut pour les deux.

Où vit le plan : chez le client, jamais chez nous.
    ~/.local/share/wallet-client/book/plans/<SYMBOLE>.json   (ou WALLET_CLIENT_BOOK)
    ~/.local/share/wallet-client/book/plan-events.jsonl      journal, en ajout seul

Premier lot : les plans des lignes DÉTENUES (le conid vient du rapport Flex). Une
idée d'achat non détenue attendra une recherche de conid.
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
import client_prices  # noqa: E402
import decision_schema  # noqa: E402  # type: ignore[import-not-found]
import price_cache  # noqa: E402  # type: ignore[import-not-found]
import tripwires  # noqa: E402  # type: ignore[import-not-found]

LIVE_STATUSES = ("armed", "TRIGGERED", "RETURNED")


def book_dir() -> pathlib.Path:
    configured = os.environ.get("WALLET_CLIENT_BOOK")
    return pathlib.Path(configured).expanduser() if configured else (
        pathlib.Path.home() / ".local" / "share" / "wallet-client" / "book")


def plan_path(symbol: str) -> pathlib.Path:
    return book_dir() / "plans" / f"{symbol}.json"


def read_plan(symbol: str) -> dict | None:
    try:
        return json.loads(plan_path(symbol).read_text(encoding="utf-8")).get("decision")
    except (FileNotFoundError, json.JSONDecodeError):
        return None


def append_event(event: str, symbol: str, **extra: object) -> None:
    """Le journal des plans du client, en ajout seul : la trace de chaque réécriture."""
    path = book_dir() / "plan-events.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    entry = {"at": datetime.datetime.now(datetime.UTC).isoformat(timespec="seconds"),
             "event": event, "symbol": symbol, **extra}
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(entry, ensure_ascii=False) + "\n")


def held_lines(**options) -> tuple[list[dict] | None, str | None, str | None]:
    """(positions du rapport Flex, date du rapport, erreur)."""
    book = client_book.load_book(**options)
    if "error" in book:
        return None, None, book["error"]
    return book["snapshot"]["positions"], book["snapshot"]["date"], None


def ticker(position: dict) -> str:
    return position["contract_description"].split(" @")[0].upper()


def find_held(symbol: str, **options) -> tuple[dict | None, str | None]:
    positions, date, error = held_lines(**options)
    if error:
        return None, error
    wanted = symbol.strip().upper()
    for position in positions:
        if ticker(position) == wanted:
            return position, None
    return None, f"{wanted} is not a holding (Flex report of {date})"


def evaluate(symbol: str, conid: int, level: dict, getter, now: datetime.datetime) -> dict:
    """État d'un niveau sur les clôtures réglées : statut, seuil effectif, clôture, distance."""
    folder = client_book.state_dir() / "series"
    found = client_prices.series(conid, folder, getter, now)
    if "error" in found:
        return {"status": "UNVERIFIABLE", "why": found["error"]}
    # La loi lit le cache par conid sous `price_cache.CACHE_DIR` : on la pointe sur celui
    # du client, le seul que ce processus sert.
    price_cache.CACHE_DIR = folder
    universe = {symbol: {"conid": conid}}
    status, message = tripwires.check_level(symbol, level, universe, today=now.date())
    out = {"status": status, "why": message.split(" — ")[0] if status not in LIVE_STATUSES else None}
    if status in LIVE_STATUSES:
        bars, why = tripwires._bars(universe, symbol, level["bar"], today=now.date())
        if not why:
            close, as_of, _ = tripwires.settled_close(bars, level["bar"])
            px, _ = tripwires.level_px(level, bars)
            out.update(threshold=round(px, 4), close=close, close_date=as_of,
                       distance_pct=round((px / close - 1) * 100, 2) if close else None)
    if found.get("stale_error"):
        out["note"] = f"price server unreachable, keeping the cached series: {found['stale_error']}"
    return out


def describe(symbol: str, conid: int, decision: dict, getter, now: datetime.datetime) -> dict:
    levels = []
    for level in decision.get("levels") or []:
        state = evaluate(symbol, conid, level, getter, now)
        levels.append({"label": level.get("label") or level.get("action"),
                       "rule": f"{level['bar']} {level['op']} " + (
                           f"{level['px']}" if "px" in level else
                           f"sma{level['sma']['window']}" if "sma" in level else
                           f"palier (seed {level['trail']['seed']})"),
                       "effect": decision_schema.level_effect(level),
                       "action": level.get("action"), **state})
    return {"symbol": symbol, "status": decision.get("status"), "horizon": decision.get("horizon"),
            "thesis": decision.get("thesis"), "if_hit": decision.get("if_hit"),
            "if_miss": decision.get("if_miss"), "next_decision": decision.get("next_decision"),
            "review_by": decision.get("review_by"), "activated_on": decision.get("activated_on"),
            "no_levels_reason": decision.get("no_levels_reason"), "levels": levels}


def get_plan(symbol: str, getter=None, *, now: datetime.datetime | None = None) -> dict:
    now = now or client_book.now_utc()
    position, error = find_held(symbol, now=now)
    if error:
        return {"error": error}
    sym = ticker(position)
    decision = read_plan(sym)
    if not decision:
        return {"symbol": sym, "plan": None,
                "next": "no plan: write one with `set_plan` after looking at `weekly_chart`"}
    if getter is None:
        getter, error = client_prices.server_getter(client_book.read_config()[0] or {})
        if error:
            return {"error": error}
    return describe(sym, position["contract_id"], decision, getter, now)


def set_plan(symbol: str, thesis: str, horizon: str, if_hit: str, if_miss: str,
             next_decision: str, levels: list[str] | None = None,
             no_levels_reason: str | None = None, review_by: str | None = None,
             reason: str | None = None, *, now: datetime.datetime | None = None) -> dict:
    """Écrit le plan actif d'une ligne détenue, validé par le contrat du produit."""
    now = now or client_book.now_utc()
    position, error = find_held(symbol, now=now)
    if error:
        return {"error": error}
    sym = ticker(position)
    try:
        parsed = [dict(decision_schema.parse_level(spec), set_by=decision_schema.SET_BY_AGENT)
                  for spec in (levels or [])]
    except (decision_schema.SchemaError, ValueError) as failure:
        return {"error": f"unreadable level: {failure}",
                "format": "\"1W < 140 (memory) [exit] exit on a weekly close below 140\""}
    previous = read_plan(sym) or {}
    block = {"status": decision_schema.STATUS_ACTIVE, "horizon": horizon, "thesis": thesis,
             "if_hit": if_hit, "if_miss": if_miss, "next_decision": next_decision,
             "levels": parsed,
             "activated_on": previous.get("activated_on") or now.date().isoformat()}
    if no_levels_reason:
        block["no_levels_reason"] = no_levels_reason
    if review_by:
        block["review_by"] = review_by
    try:
        decision = decision_schema.validate_decision(block, sym)
    except decision_schema.SchemaError as failure:
        return {"error": "plan rejected, nothing was written", "violations": str(failure).splitlines()}
    path = plan_path(sym)
    path.parent.mkdir(parents=True, exist_ok=True)
    with atomic_file.locked(path):
        atomic_file.write_text(path, json.dumps(
            {"symbol": sym, "conid": position["contract_id"], "decision": decision,
             "updated_on": now.date().isoformat()}, indent=2, ensure_ascii=False) + "\n")
    append_event("plan_saved", sym, levels=len(parsed), horizon=horizon,
                 **({"reason": reason.strip()} if reason else {}))
    exits = [lv for lv in decision.get("levels") or []
             if decision_schema.level_effect(lv) == decision_schema.EFFECT_EXIT]
    return {"written": sym, "levels": len(parsed),
            "warning": None if exits else "no exit level: the line still has no written exit"}


def overview(getter=None, *, now: datetime.datetime | None = None) -> dict:
    """Chaque ligne détenue face à son plan : ce qui a franchi, ce qui n'a pas de sortie."""
    now = now or client_book.now_utc()
    positions, date, error = held_lines(now=now)
    if error:
        return {"error": error}
    if getter is None:
        getter, _ = client_prices.server_getter(client_book.read_config()[0] or {})
    crossed, no_plan, no_exit, armed = [], [], [], []
    for position in positions:
        sym = ticker(position)
        decision = read_plan(sym)
        if not decision or decision.get("status") != decision_schema.STATUS_ACTIVE:
            no_plan.append(sym)
            continue
        if getter is None:
            armed.append({"symbol": sym, "note": "price server not configured: levels not evaluated"})
            continue
        plan = describe(sym, position["contract_id"], decision, getter, now)
        fired = [lv for lv in plan["levels"] if lv["status"] == "TRIGGERED"]
        exits = [lv for lv in plan["levels"] if lv["effect"] == decision_schema.EFFECT_EXIT]
        if fired:
            crossed.append({"symbol": sym, "levels": [
                {key: lv.get(key) for key in ("label", "rule", "effect", "action", "close", "close_date")}
                for lv in fired], "if_miss": plan["if_miss"]})
        elif not exits:
            no_exit.append(sym)
        else:
            nearest = min((lv for lv in exits if lv.get("distance_pct") is not None),
                          key=lambda lv: abs(lv["distance_pct"]), default=None)
            armed.append({"symbol": sym, "exit": nearest and {
                key: nearest.get(key) for key in ("rule", "threshold", "close", "close_date", "distance_pct")}})
    return {"report_date": date, "crossed": crossed, "without_plan": no_plan,
            "without_exit": no_exit, "armed": armed}


def chart_levels(symbol: str, conid: int, getter, now: datetime.datetime) -> list[dict]:
    """Les seuils effectifs du plan, pour les tracer sur le graphique."""
    decision = read_plan(symbol)
    if not decision:
        return []
    out = []
    for level in decision.get("levels") or []:
        state = evaluate(symbol, conid, level, getter, now)
        if state.get("threshold") is not None:
            out.append({"px": state["threshold"], "effect": decision_schema.level_effect(level),
                        "label": level.get("label") or level.get("action")})
    return out
