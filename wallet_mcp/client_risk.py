"""Le risque d'un client face à ses plans : ce que coûte chaque sortie écrite.

POURQUOI (2026-11-07, décision du propriétaire : « tous les tools possibles »). Un plan
dit OÙ sortir ; il ne dit pas COMBIEN cela coûte. Le risque d'une ligne est l'argent
perdu si elle va jusqu'à sa sortie, rapporté au livre : une ligne de 2 % à 30 % de sa
sortie pèse moins qu'une ligne de 10 % à 8 %. Une ligne sans sortie a un risque NON
BORNÉ : c'est elle qui se dit en premier, pas la plus grosse perte bornée.

LES SOURCES, toutes chez le client : la position et son prix de marquage (rapport
Flex), le plan et ses seuils évalués sur nos clôtures réglées (`client_plans`). La
valeur à la sortie se calcule par le rapport des prix (seuil ÷ marquage), ce qui
garde la devise de base sans taux de change à refaire.

Aussi ici : les plans dont la revue tombe (`reviews_due`) et l'historique d'un plan
(`plan_history`), lus dans le livre local du client.
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

import client_book  # noqa: E402
import client_plans  # noqa: E402
import client_prices  # noqa: E402
import decision_schema  # noqa: E402  # type: ignore[import-not-found]

#: Une revue « bientôt » : dans les deux semaines.
SOON_DAYS = 14
#: Un plan sans date de revue et plus vieux que cela mérite d'être relu.
STALE_DAYS = 180


def exit_levels(plan: dict) -> list[dict]:
    return [level for level in plan.get("levels") or []
            if level.get("effect") == decision_schema.EFFECT_EXIT and level.get("threshold")]


def line_risk(position: dict, row: dict, plan: dict | None, book_value: float | None) -> dict:
    """Le risque d'une ligne jusqu'à sa sortie la plus proche, en devise de base."""
    sym = client_plans.ticker(position)
    out = {"symbol": sym, "weight_cost_pct": row.get("weight_cost_pct"),
           "value_base": row.get("value_base"), "pnl_pct": row.get("pnl_pct")}
    if plan is None:
        return {**out, "risk": "unbounded", "why": "no active plan"}
    exits = exit_levels(plan)
    if not exits:
        return {**out, "risk": "unbounded", "why": "the plan has no exit level"}
    mark, value, cost = position.get("market_price"), row.get("value_base"), row.get("cost_base")
    long = (position.get("position") or 0) >= 0
    # La sortie la plus proche du côté où le prix doit aller pour la toucher.
    reachable = [level for level in exits if (level["threshold"] <= (level.get("close") or mark)) == long]
    nearest = min(reachable or exits, key=lambda level: abs(level.get("distance_pct") or 0))
    out["exit"] = {key: nearest.get(key) for key in
                   ("rule", "threshold", "close", "close_date", "distance_pct", "status")}
    if nearest.get("status") == "TRIGGERED":
        out["note"] = "this exit already crossed on a settled close: the plan says to act"
    if not mark or value is None:
        return {**out, "risk": "unknown", "why": "no mark price in the Flex report"}
    value_at_exit = value * nearest["threshold"] / mark
    loss = value_at_exit - value
    out.update(risk="bounded",
               loss_to_exit_base=round(loss, 2),
               loss_to_exit_pct_of_book=round(loss / book_value * 100, 2) if book_value else None,
               pnl_at_exit_base=round(value_at_exit - cost, 2) if cost is not None else None)
    return out


def context(now: datetime.datetime) -> tuple[dict | None, str | None]:
    book = client_book.load_book(now=now)
    if "error" in book:
        return None, book["error"]
    snapshot = book["snapshot"]
    rows = {row["symbol"]: row for row in client_book.lines(snapshot)}
    nav = client_book.amount(snapshot["summary"].get("net_liquidation"))
    total = sum(row["value_base"] for row in rows.values() if row["value_base"] is not None)
    return {"snapshot": snapshot, "rows": rows, "book_value": nav or total,
            "book_value_is": "net liquidation value" if nav else "sum of holdings (no cash report)"}, None


def plan_of(position: dict, getter, now: datetime.datetime) -> dict | None:
    sym = client_plans.ticker(position)
    decision = client_plans.read_plan(sym)
    if not decision or decision.get("status") != decision_schema.STATUS_ACTIVE:
        return None
    return client_plans.describe(sym, position["contract_id"], decision, getter, now)


def position_risk(symbol: str, getter=None, *, now: datetime.datetime | None = None) -> dict:
    now = now or client_book.now_utc()
    found, error = context(now)
    if error:
        return {"error": error}
    wanted = symbol.strip().upper()
    position = next((p for p in found["snapshot"]["positions"] if client_plans.ticker(p) == wanted), None)
    if position is None:
        return {"error": f"{wanted} is not a holding (Flex report of {found['snapshot']['date']})"}
    if getter is None:
        getter, error = client_prices.server_getter(client_book.read_config()[0] or {})
        if error:
            return {"error": error}
    row = found["rows"][position["contract_description"]]
    result = line_risk(position, row, plan_of(position, getter, now), found["book_value"])
    return {"report_date": found["snapshot"]["date"], "base_currency": found["snapshot"]["fx"]["base"],
            "book_value_is": found["book_value_is"], **result}


def book_risk(getter=None, *, now: datetime.datetime | None = None) -> dict:
    now = now or client_book.now_utc()
    found, error = context(now)
    if error:
        return {"error": error}
    if getter is None:
        getter, error = client_prices.server_getter(client_book.read_config()[0] or {})
        if error:
            return {"error": error}
    risks = [line_risk(position, found["rows"][position["contract_description"]],
                       plan_of(position, getter, now), found["book_value"])
             for position in found["snapshot"]["positions"]]
    bounded = sorted((r for r in risks if r["risk"] == "bounded"), key=lambda r: r["loss_to_exit_base"])
    unbounded = sorted((r for r in risks if r["risk"] != "bounded"),
                       key=lambda r: r.get("weight_cost_pct") or 0, reverse=True)
    total = sum(r["loss_to_exit_base"] for r in bounded)
    value = found["book_value"]
    return {"report_date": found["snapshot"]["date"], "base_currency": found["snapshot"]["fx"]["base"],
            "book_value": round(value, 2) if value else None, "book_value_is": found["book_value_is"],
            "loss_if_every_exit_hits_base": round(total, 2),
            "loss_if_every_exit_hits_pct": round(total / value * 100, 2) if value else None,
            "unbounded": [{key: r.get(key) for key in ("symbol", "weight_cost_pct", "value_base", "why")}
                          for r in unbounded],
            "unbounded_value_pct": round(sum(r.get("value_base") or 0 for r in unbounded) / value * 100, 2)
            if value else None,
            "bounded_by_loss": bounded,
            "reading": ("unbounded holdings come first: without a written exit their loss has no "
                        "limit; then the largest losses to exit")}


def reviews_due(*, now: datetime.datetime | None = None) -> dict:
    """Les plans des lignes détenues à relire : revue dépassée, proche, ou jamais datée."""
    now = now or client_book.now_utc()
    positions, date, error = client_plans.held_lines(now=now)
    if error:
        return {"error": error}
    today = now.date()
    overdue, soon, undated, without_plan = [], [], [], []
    for position in positions:
        sym = client_plans.ticker(position)
        decision = client_plans.read_plan(sym)
        if not decision:
            without_plan.append(sym)
            continue
        entry = {"symbol": sym, "review_by": decision.get("review_by"),
                 "activated_on": decision.get("activated_on"), "thesis": decision.get("thesis"),
                 "next_decision": decision.get("next_decision")}
        try:
            due = datetime.date.fromisoformat(decision["review_by"]) if decision.get("review_by") else None
        except ValueError:
            due = None
        if due is not None:
            days = (due - today).days
            if days < 0:
                overdue.append({**entry, "days_overdue": -days})
            elif days <= SOON_DAYS:
                soon.append({**entry, "days_left": days})
            continue
        try:
            age = (today - datetime.date.fromisoformat(decision.get("activated_on") or "")).days
        except ValueError:
            age = None
        undated.append({**entry, "plan_age_days": age, "stale": age is not None and age > STALE_DAYS})
    return {"report_date": date, "today": today.isoformat(), "overdue": overdue, "soon": soon,
            "without_review_date": undated, "without_plan": without_plan,
            "how": ("a review re-reads the thesis against the weekly chart and the news; "
                    "rewrite the plan with `set_plan` and a new `review_by`")}


def plan_history(symbol: str) -> dict:
    """Chaque écriture du plan d'une ligne, du journal local du client, la plus récente d'abord."""
    wanted = symbol.strip().upper()
    path = client_plans.book_dir() / "plan-events.jsonl"
    events = []
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            try:
                event = json.loads(line)
            except ValueError:
                continue
            if event.get("symbol") == wanted:
                events.append(event)
    except FileNotFoundError:
        pass
    return {"symbol": wanted, "current": client_plans.read_plan(wanted),
            "events": list(reversed(events)),
            "note": None if events else "no plan was ever written for this symbol on this machine"}
