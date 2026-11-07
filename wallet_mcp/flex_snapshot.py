"""Snapshot de séance reconstruit depuis le rapport Flex — sans le gateway."""

from __future__ import annotations

import csv
import datetime
import io
import json
from pathlib import Path




_US_VENUES = {"NASDAQ", "NYSE", "ARCA", "BATS", "AMEX", "PINK", "IEX", "PSE", "NYSENAT"}





DAILY_PCT_UNIT_KEY = "daily_pct_unit"
DAILY_PCT_UNIT = "points"


def _f(x) -> float | None:
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def names_from_snapshots(snap_dir: Path) -> dict[int, str]:
    """conid → description, apprise des snapshots gateway déjà archivés."""
    names: dict[int, str] = {}
    for path in sorted(snap_dir.glob("*.json")):
        try:
            snap = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if snap.get("source") == "flex":
            continue
        for p in snap.get("positions") or []:
            cid, desc = p.get("contract_id"), p.get("contract_description")
            if cid and desc:
                names[cid] = desc
    return names


def cash_from_report(csv_text: str) -> tuple[float | None, str | None]:
    """Cash de clôture en devise de base, depuis le rapport Cash Report."""
    total, seen, bad = 0.0, set(), False
    for r in csv.DictReader(io.StringIO(csv_text)):
        if r.get("CurrencyPrimary") != "BASE_SUMMARY":
            continue
        account = r.get("ClientAccountID") or f"#{len(seen)}"
        if account in seen:
            continue
        seen.add(account)
        v = _f(r.get("EndingCash"))
        if v is None:
            bad = True
            continue
        total += v
    if bad:
        return None, "EndingCash illisible"
    if not seen:
        return None, "ligne BASE_SUMMARY absente du rapport cash"
    return total, None


def prev_marks(snap_dir: Path, session: str) -> dict[int, float]:
    """conid → market_price de la dernière séance archivée AVANT `session`."""
    marks: dict[int, float] = {}
    prev = [p for p in sorted(snap_dir.glob("*.json")) if p.stem < session]
    if not prev:
        return marks
    try:
        snap = json.loads(prev[-1].read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return marks
    for p in snap.get("positions") or []:
        cid, mp = p.get("contract_id"), p.get("market_price")
        if cid and isinstance(mp, (int, float)) and mp:
            marks[cid] = mp
    return marks


def _consolidated(rows: list[dict]) -> list[dict]:
    """Une ligne SUMMARY par conid, les comptes additionnés (2026-10-14)."""
    by_conid: dict[str, list[dict]] = {}
    order: list[str] = []
    for r in rows:
        key = r.get("Conid") or ""
        if key not in by_conid:
            order.append(key)
        by_conid.setdefault(key, []).append(r)
    out = []
    for key in order:
        group = by_conid[key]
        accounts = {r.get("ClientAccountID") for r in group}
        if len(group) == 1 or not key or len(accounts) < len(group):
            out.extend(group)
            continue
        merged = dict(group[0])
        for field in ("Quantity", "PositionValue", "CostBasisMoney"):
            values = [_f(r.get(field)) for r in group]
            merged[field] = None if any(v is None for v in values) else repr(sum(values))
        qty, cost = _f(merged.get("Quantity")), _f(merged.get("CostBasisMoney"))
        merged["CostBasisPrice"] = repr(cost / qty) if qty and cost is not None else None
        out.append(merged)
    return out


def build(
    csv_text: str,
    names: dict[int, str] | None = None,
    cash_text: str | None = None,
    prev: dict[int, float] | None = None,
    base: str = "EUR",
) -> tuple[dict | None, str | None]:
    """Rapport Flex (texte CSV) → dict au format snapshot. (data, error)."""
    rows = list(csv.DictReader(io.StringIO(csv_text)))
    summary = [r for r in rows if r.get("LevelOfDetail") == "SUMMARY"]
    if not summary:
        return None, "aucune ligne SUMMARY dans le rapport Flex"
    dates = {r.get("ReportDate") for r in summary if r.get("ReportDate")}
    if len(dates) != 1:
        return None, f"ReportDate ambigu : {sorted(dates)[:5]}"
    d = dates.pop()
    session = f"{d[:4]}-{d[4:6]}-{d[6:]}"

    positions, rates, skipped = [], {}, []
    summary = _consolidated(summary)
    for r in summary:
        qty, mark = _f(r.get("Quantity")), _f(r.get("MarkPrice"))
        val, cost = _f(r.get("PositionValue")), _f(r.get("CostBasisMoney"))
        fx = _f(r.get("FXRateToBase"))
        ccy, conid = r.get("CurrencyPrimary"), r.get("Conid")
        if not conid or qty is None:
            continue
        try:
            cid = int(conid)
        except ValueError:


            skipped.append(r.get("Symbol") or conid)
            continue
        if ccy and fx is not None:
            rates[ccy] = fx
        pm = (prev or {}).get(cid)


        daily_pct = ((mark / pm - 1) * 100) if (pm and mark is not None) else None
        daily_pnl = ((mark - pm) * qty) if (pm and mark is not None) else None
        desc = (names or {}).get(cid)
        if not desc:
            desc = r.get("Symbol") or ""
            venue = (r.get("ListingExchange") or "").upper()
            if venue and venue not in _US_VENUES:
                desc = f"{desc} @{venue}"
        positions.append(
            {
                "contract_id": cid,
                "contract_description": desc,
                "position": qty,
                "market_price": mark,
                "market_value": val,
                "currency": ccy,
                "average_price": _f(r.get("CostBasisPrice")),

                "unrealized_pnl": (val - cost) if (val is not None and cost is not None) else None,

                "daily_pnl": round(daily_pnl, 2) if daily_pnl is not None else None,
                "daily_pct": round(daily_pct, 6) if daily_pct is not None else None,
                "asset_class": r.get("AssetClass"),
                "verified": False,
            }
        )
    if not positions:
        return None, "rapport Flex sans position exploitable"

    gross = sum(
        (p["market_value"] or 0) * (rates.get(p["currency"]) or 0) for p in positions
    )





    cash = cash_err = None
    if cash_text:
        cash, cash_err = cash_from_report(cash_text)



    summary = {
        "gross_position_value": {"amount": round(gross, 2), "currency": base},
        "total_cash_value": {"amount": round(cash, 2), "currency": base} if cash is not None else None,


        "net_liquidation": {"amount": round(gross + cash, 2), "currency": base}
        if cash is not None and not skipped
        else None,
    }
    notes = []
    if cash is None:
        notes.append(f"reconstruit du Flex sans le rapport cash ({cash_err or 'absent'}) — NAV indisponible")
    if skipped:
        notes.append(f"ligne(s) au Conid illisible écartée(s), NAV indisponible : "
                     f"{', '.join(map(str, skipped))}")
    if notes:
        summary["note"] = " ; ".join(notes)
    return {
        "date": session,
        "captured_at": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"),
        "source": "flex",



        DAILY_PCT_UNIT_KEY: DAILY_PCT_UNIT,
        "summary": summary,
        "fx": {"base": base, "rates": dict(sorted(rates.items()))},
        "allocation": None,
        "positions": positions,
    }, None


def build_from_file(
    path: Path,
    names: dict[int, str] | None = None,
    cash_path: Path | None = None,
    prev: dict[int, float] | None = None,
) -> tuple[dict | None, str | None]:
    """`cash_path` doit porter LA MÊME séance que `path` — l'appelant apparie sur"""
    try:
        cash_text = None
        if cash_path and cash_path.exists():
            cash_text = cash_path.read_text(encoding="utf-8")
        return build(path.read_text(encoding="utf-8"), names, cash_text, prev)
    except OSError as e:
        return None, f"{path.name} illisible : {e}"
