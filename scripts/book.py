#!/usr/bin/env python3
"""La plomberie commune des scripts wallet — snapshot, lots Flex, cohortes, répertoire de données."""
from __future__ import annotations
import csv, datetime, json, pathlib

from derived_cache import DerivedCache, files_signature
import _drawdowns
import data_root
import now as market_time

HERE = pathlib.Path(__file__).resolve().parent
SKILL = HERE.parent









DAILY_PCT_UNIT_KEY = "daily_pct_unit"
DAILY_PCT_POINTS = "points"


def data_path() -> pathlib.Path:
    """Le répertoire de données CONFIGURÉ, sans exiger qu'il existe."""
    return data_root.data_path()


def data_dir() -> pathlib.Path:
    """Le répertoire de données du dashboard. Relatif au dépôt depuis la fusion"""
    d = data_path()
    if not d.is_dir():
        raise SystemExit(
            f"Répertoire de données introuvable : {d}\n"
            f"Le dashboard y tient le ledger, les snapshots et les exports Flex. "
            f"S'il a bougé, pointer WALLET_DATA sur son répertoire backend/data.")
    return d


def daily_pct_to_points(value, unit, source):
    """Le jour % d'une ligne ramené en POINTS de pourcentage."""
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        return value
    if unit == DAILY_PCT_POINTS:
        return value
    if unit is None and source == "flex":
        return value * 100
    return value


def position_symbol(description) -> str:
    """Le symbole d'une position IBKR : sa description sans la place (` @TASE`)."""
    return str(description or "").split("@")[0].strip()


def load_snapshot(path) -> dict:
    """One snapshot, parsed once for everyone."""
    return parse_snapshot(json.loads(pathlib.Path(path).read_text()), path)


def parse_snapshot(d: dict, path="snapshot") -> dict:
    """`load_snapshot` sur un snapshot déjà lu ; `path` ne sert qu'aux messages."""
    fx = d["fx"]["rates"]
    unit, source = d.get(DAILY_PCT_UNIT_KEY), d.get("source")
    lines = {}
    for p in d["positions"]:
        sym = position_symbol(p["contract_description"])






        if sym in lines:
            raise SystemExit(
                f"Snapshot {path}: deux positions portent le symbole « {sym} » "
                f"(conids {lines[sym]['conid']} et {p.get('contract_id')}).\n"
                "  La seconde écraserait la première et total_cost perdrait une "
                "ligne — les poids au coût seraient faux pour tout le livre.\n"
                "  Cas légitime (deux cotations du même titre détenues ensemble) : "
                "trancher comment les distinguer, puis lever cette garde exprès.")
        r = fx_rate(fx, p["currency"], d["fx"].get("base", "EUR"), path)
        lines[sym] = {
            "contract_description": p["contract_description"],
            "qty": p["position"],
            "cost": p["average_price"] * p["position"] * r,
            "value": p["market_value"] * r,


            "value_local": p["market_value"],
            "pnl": (p.get("unrealized_pnl") or 0) * r,
            "daily_pct": daily_pct_to_points(p.get("daily_pct"), unit, source),
            "verified": p.get("verified"),
            "currency": p["currency"],
            "conid": str(p.get("contract_id", "")),
            "price": p.get("market_price"),
            "average_price": p.get("average_price"),
        }
    total = sum(v["cost"] for v in lines.values()) or 1
    for v in lines.values():
        v["w_cost"] = v["cost"] / total * 100


    nav = d["summary"]["net_liquidation"]
    if isinstance(nav, dict):
        nav = nav.get("amount")
    return {"date": d["date"], "captured_at": d.get("captured_at"), "nav": nav,
            "base": d["fx"].get("base", "EUR"), "total_cost": total,
            "lines": lines}


def fx_rate(rates, currency, base="EUR", source="snapshot"):
    """Taux de conversion vers la devise de base — jamais deviné."""
    if currency == base:
        return 1.0
    if currency not in rates:
        raise SystemExit(
            f"{source} : aucun taux {currency}->{base} — une ligne valorisée au pair "
            "fausserait tous les poids au coût. Réparer la source des taux.")
    return rates[currency]


def session_snapshots(directory=None) -> list[pathlib.Path]:
    """Les snapshots datés d'une SÉANCE US, du plus ancien au plus récent."""
    root = pathlib.Path(directory) if directory else data_dir() / "snapshots"
    paths = []
    for path in sorted(root.glob("????-??-??.json")):
        try:
            day = datetime.date.fromisoformat(path.stem)
        except ValueError:
            continue
        if market_time.is_us_session(day):
            paths.append(path)
    return paths


def latest_snapshot(directory=None) -> pathlib.Path | None:
    """Le snapshot de la dernière SÉANCE US, ou None — le seul « dernier snapshot »."""
    snapshots = session_snapshots(directory)
    return snapshots[-1] if snapshots else None


def latest_session_snapshot(directory=None) -> pathlib.Path:
    """Le snapshot de la dernière SÉANCE, ou un refus qui dit ce qui manque."""
    paths = session_snapshots(directory)
    if not paths:
        root = pathlib.Path(directory) if directory else data_dir() / "snapshots"
        raise FileNotFoundError(
            f"aucun snapshot de SÉANCE dans {root} — le backend en écrit un "
            f"après la clôture US ; sans lui il n'y a pas de livre réel à comparer.")
    return paths[-1]


def reconciled_holdings_report(snapshot_path, ledger_path=None) -> tuple[dict[str, dict], list[dict]]:
    """Détentions locales après les fills postérieurs au snapshot."""
    snapshot = load_snapshot(snapshot_path)
    holdings: dict[str, dict] = {}
    anomalies: list[dict] = []
    last_fill: dict[str, tuple] = {}
    for symbol, line in snapshot["lines"].items():
        conid = str(line.get("conid") or "")
        key = conid or symbol
        holdings[key] = {
            "symbol": symbol,
            "conid": int(conid) if conid.isdigit() else conid or None,
            "quantity": float(line.get("qty") or 0),
        }

    path = pathlib.Path(ledger_path) if ledger_path else None
    if path and path.exists():
        captured_at = str(snapshot.get("captured_at") or "")
        for raw in path.read_text(encoding="utf-8").splitlines():
            try:
                fill = json.loads(raw)
                trade_time = str(fill.get("trade_time") or "")
                if captured_at:
                    trade_dt = datetime.datetime.fromisoformat(
                        trade_time.replace("Z", "+00:00"))
                    captured_dt = datetime.datetime.fromisoformat(
                        captured_at.replace("Z", "+00:00"))
                    if trade_dt <= captured_dt:
                        continue
                elif trade_time[:10] <= snapshot["date"]:
                    continue
                conid = str(fill.get("conid") or "")
                symbol = str(fill.get("symbol") or "").upper()
                key = conid or symbol
                quantity = float(fill.get("size") or 0)
                side = str(fill.get("side") or "").upper()
            except (TypeError, ValueError, json.JSONDecodeError):
                continue
            if not key or not symbol or not quantity or side not in {"BUY", "SELL"}:
                continue
            if str(fill.get("sec_type") or "").upper() == "CASH":
                continue
            if key not in holdings:
                if side != "BUY":
                    anomalies.append({
                        "kind": "sell_unknown_key", "symbol": symbol,
                        "conid": int(conid) if conid.isdigit() else conid or None,
                        "quantity": quantity, "trade_id": fill.get("trade_id"),
                        "trade_time": trade_time,
                    })
                    continue
                holdings[key] = {
                    "symbol": symbol,
                    "conid": int(conid) if conid.isdigit() else conid or None,
                    "quantity": 0.0,
                }
            holdings[key]["quantity"] += quantity if side == "BUY" else -quantity
            if holdings[key]["quantity"] < -1e-6:
                last_fill[key] = (fill.get("trade_id"), trade_time)

    for key, row in holdings.items():
        if row["quantity"] < -1e-6:
            trade_id, trade_time = last_fill.get(key, (None, None))
            anomalies.append({
                "kind": "oversold", "symbol": row["symbol"], "conid": row["conid"],
                "quantity": row["quantity"], "trade_id": trade_id, "trade_time": trade_time,
            })
    held = {
        row["symbol"]: row
        for row in holdings.values()
        if row["quantity"] > 1e-6
    }
    return held, anomalies


def reconciled_holdings(snapshot_path, ledger_path=None) -> dict[str, dict]:
    """Détentions locales après les fills postérieurs au snapshot — la doctrine"""
    return reconciled_holdings_report(snapshot_path, ledger_path)[0]




SOLD_RESIDUAL_MAX_WEIGHT_PCT = 0.1


def sold_residuals(snapshot_path, holdings: dict, records: dict) -> set[str]:
    """Les symboles encore au livre dont la décision est soldée et le reste négligeable."""
    lines = load_snapshot(snapshot_path)["lines"]
    residuals = set()
    for symbol, holding in holdings.items():
        plan = (records.get(symbol) or {}).get("plan") or {}
        line = lines.get(symbol)
        if plan.get("status") != "closed" or not line:
            continue
        if float(holding.get("quantity") or 0) > float(line.get("qty") or 0) + 1e-6:
            continue
        if float(line.get("w_cost") or 0) < SOLD_RESIDUAL_MAX_WEIGHT_PCT:
            residuals.add(symbol)
    return residuals






def snapshot_amounts(snapshot_path, weighting: str = "cost") -> tuple[str, dict]:
    """(date, {symbole: montant}) d'un snapshot, au coût ou au marché, en"""
    if weighting not in {"cost", "market"}:
        raise ValueError(f"pondération inconnue : {weighting}")
    snap = load_snapshot(snapshot_path)
    field = "cost" if weighting == "cost" else "value"
    return snap["date"], {symbol: row[field] for symbol, row in snap["lines"].items()}





UNCLASSIFIED_LABEL = "Non classé"


def is_classified(ref: dict, symbol: str, field: str, buckets) -> bool:
    """La ligne a une fiche, le champ, et une valeur que le registre connaît."""
    value = (ref.get(symbol) or {}).get(field)
    return isinstance(value, str) and value in buckets


def allocation_input(amounts: dict, ref: dict, *, field: str, buckets, field_label: str,
                     bucket_label: str, weighting: str, unclassified: bool = False) -> tuple:
    """Charpente commune de `sectors.allocation` et `geo.allocation` (2026-10-04)."""
    if weighting not in {"cost", "market"}:
        raise ValueError(f"pondération inconnue : {weighting}")
    ref = dict(ref)
    ref.pop("_meta", None)
    if not unclassified:
        unknown = [s for s in amounts if s not in ref]
        if unknown:
            raise ValueError(f"Fiche instrument absente — classer d'abord : {', '.join(sorted(unknown))}")
        missing = sorted(s for s in amounts if field not in ref[s])
        if missing:
            raise ValueError(f"Champ {field_label} absent — classer d'abord : {', '.join(missing)}")
        bad = sorted({ref[s][field] for s in amounts if ref[s][field] not in buckets})
        if bad:
            raise ValueError(f"{bucket_label}, refus de deviner : {', '.join(bad)}")
    total = sum(amounts.values())
    if total <= 0:
        raise ValueError("montant total nul — allocation impossible")
    if weighting == "cost":
        return ref, total, "cost", "total_cost"
    return ref, total, "market_value", "total_market_value"


def bucket_rows(groups: dict, order, total: float, amount_key: str) -> list[dict]:
    """[{label, lines, <montant>, pct, symbols}] dans l'ordre déclaré."""
    return [{"label": k, "lines": groups[k][0], amount_key: round(groups[k][1], 2),
             "pct": round(groups[k][1] / total * 100, 2), "symbols": sorted(groups[k][2])}
            for k in order if k in groups]


BANDS = ((21, "<3 semaines"), (90, "<3 mois"), (180, "<6 mois"),
         (365, "<1 an"))
LAST_BAND = ">1 an"
BAND_ORDER = [label for _, label in BANDS] + [LAST_BAND]


def cohort_of(open_date: str, today: datetime.date) -> str:
    age = (today - datetime.date.fromisoformat(open_date)).days
    for limit, label in BANDS:
        if age < limit:
            return label
    return LAST_BAND


def load_flex_lots(path) -> dict:
    """{conid: ISO open date of the OLDEST lot still held}."""
    first = {}
    with open(path) as fh:
        for r in csv.DictReader(fh):
            if r.get("LevelOfDetail") != "LOT":
                continue
            d, c = r["OpenDateTime"][:8], r["Conid"]
            if d and c and (c not in first or d < first[c]):
                first[c] = d
    return {c: f"{d[:4]}-{d[4:6]}-{d[6:8]}" for c, d in first.items()}


def flex_accounts(path) -> set:
    """Les comptes RÉELLEMENT couverts par un export Flex LOT."""
    seen = set()
    with open(path) as fh:
        for r in csv.DictReader(fh):
            if _is_header_row(r):
                continue
            account = (r.get("ClientAccountID") or "").strip()
            if account:
                seen.add(account)
    return seen


def _is_header_row(row: dict) -> bool:
    """Une ligne où toute valeur non vide est le NOM de sa colonne."""
    pairs = [(k, v) for k, v in row.items() if k and v]
    return bool(pairs) and all(k == v for k, v in pairs)


def flex_account_blocks(path) -> int:
    """Combien de comptes la QUERY couvre, et non combien en portent des lignes."""
    with open(path) as fh:
        return 1 + sum(1 for r in csv.DictReader(fh) if _is_header_row(r))


def latest_lots_file(flex_dir: pathlib.Path):
    """Newest lots-*.csv, or None. The caller decides how loud to be — an"""
    files = sorted(flex_dir.glob("lots-*.csv")) if flex_dir.exists() else []
    return files[-1] if files else None


def nav_drawdown(series: dict | None = None) -> dict | None:
    """Baisse du livre depuis son SOMMET, sur la ligne sans flux (TWR), en %."""
    if series is None:
        try:
            series = nav_series()
        except (SystemExit, FileNotFoundError):
            return None
    dates = series.get("dates") or []
    twr = series.get("twr") or {}
    if not dates:
        return None
    found = _drawdowns.current([twr[d] for d in dates], dates)
    last_on = found["last_on"]
    change_5d = (twr[last_on] / twr[dates[-6]] - 1) * 100 if len(dates) > 5 else None
    peak_on = found["peak_on"]
    nav = series.get("nav") or {}
    peak_nav, last_nav = nav.get(peak_on), nav.get(last_on)
    value_pct = (last_nav / peak_nav - 1) * 100 if peak_nav and last_nav is not None else None
    flows = series.get("flows") or {}
    flows_since_peak = sum(amount for day, amount in flows.items() if peak_on < day <= last_on)
    return {"pct": round(found["pct"], 4),
            "peak_on": peak_on, "last_on": last_on,
            "change_5d": None if change_5d is None else round(change_5d, 4),
            "peak_nav": peak_nav, "last_nav": last_nav,
            "value_pct": None if value_pct is None else round(value_pct, 4),
            "flows_since_peak": None if value_pct is None else round(flows_since_peak, 2)}



EXTERNAL_FLOW_TYPE = "deposits/withdrawals"


def is_external_flow(row: dict) -> bool:
    """Vrai si une ligne Cash Transactions Flex est un dépôt ou un retrait."""
    kind = (row.get("Type") or "").strip().casefold().replace("&", "/").replace(" ", "")
    if kind != EXTERNAL_FLOW_TYPE:
        return False
    return not (row.get("Description") or "").strip().upper().startswith("ADJUSTMENT:")


def nav_series(data=None) -> dict:
    """La série NAV quotidienne + la ligne « sans flux » (TWR), calculées DEPUIS"""
    flex = (data or data_dir()) / "flex"
    if not flex.exists() or not any(flex.glob("navdaily-*.csv")):
        return _nav_series_build(flex)
    return _NAV_SERIES.get(
        lambda: (str(flex.resolve()), files_signature(
            [*flex.glob("navdaily-*.csv"), *flex.glob("cashtx-*.csv")])),
        lambda: _nav_series_build(flex))


_NAV_SERIES = DerivedCache(max_entries=4)


def _nav_series_build(flex: pathlib.Path) -> dict:
    """Le calcul de `nav_series`, sans mémoire."""





    per_account: dict[tuple[str, str], float] = {}
    for f in sorted(flex.glob("navdaily-*.csv")):
        with f.open() as fh:
            rows = list(csv.DictReader(fh))
        for r in rows:
            d = r.get("ReportDate") or ""
            if not d.isdigit():
                continue
            try:
                tot = float(r.get("Total") or 0)
            except ValueError:
                continue
            if tot > 0:
                per_account[(f"{d[:4]}-{d[4:6]}-{d[6:]}", r.get("ClientAccountID") or "")] = tot
    nav: dict[str, float] = {}
    for (day, _account), tot in sorted(per_account.items()):
        nav[day] = nav.get(day, 0.0) + tot
    flows: dict[str, float] = {}
    source = "flex"
    if not nav:




        import connector_nav
        nav, flows = connector_nav.nav_and_flows(flex.parent)
        source = "connector"
    if not nav:
        raise SystemExit(
            f"Aucun navdaily-*.csv dans {flex} ni capture du connecteur dans "
            f"{flex.parent / 'connector' / 'performance'} — la query NAV (1575740) n'a "
            f"jamais été tirée, et `connector_nav.py` n'a rien archivé. Sans l'un des "
            f"deux, aucune série NAV ni ρ n'est calculable.")

    counts: dict[tuple[str, str, float], int] = {}
    for f in sorted(flex.glob("cashtx-*.csv")) if source == "flex" else ():
        per_file: dict[tuple[str, str, float], int] = {}
        with f.open() as fh:
            rows = list(csv.DictReader(fh))
        for r in rows:
            if not is_external_flow(r):
                continue
            d =(r.get("Date/Time") or r.get("DateTime") or r.get("Date") or "")[:8]
            if not d.isdigit():
                continue
            amt = float(r["Amount"]) * float(r.get("FXRateToBase") or 1)



            k = (f"{d[:4]}-{d[4:6]}-{d[6:]}", r.get("ClientAccountID") or "", amt)
            per_file[k] = per_file.get(k, 0) + 1
        for k, n in per_file.items():
            counts[k] = max(counts.get(k, 0), n)
    for (d, _account, amt), n in counts.items():
        flows[d] = flows.get(d, 0.0) + amt * n

    dates = sorted(nav)
    twr = {dates[0]: nav[dates[0]]}
    returns: dict[str, float] = {}
    for i in range(1, len(dates)):
        prev, cur = dates[i - 1], dates[i]
        base = nav[prev] + flows.get(cur, 0.0)
        r = nav[cur] / base - 1 if base > 0 else 0.0
        returns[cur] = r
        twr[cur] = twr[prev] * (1 + r)
    return {"dates": dates, "nav": nav, "twr": twr, "returns": returns, "flows": flows,
            "source": source}


def twr_return(twr: dict[str, float], start_date: str, end_date: str) -> float | None:
    """Rendement TWR entre deux dates de la réduction NAV canonique."""
    start = twr.get(start_date)
    end = twr.get(end_date)
    if start is None or end is None or start <= 0:
        return None
    return (end / start - 1) * 100





























MWR_ANNUAL_FROM_DAYS = 365
MWR_METHODS = ("irr",)
MWR_METHOD_LABELS = {
    "irr": "TRI exact par bissection",
}

MWR_REASONS = ("same_day", "no_root", "multiple_roots", "no_start")
MWR_REASON_LABELS = {
    "same_day": "période d'une seule séance : aucun rendement pondéré par l'argent",
    "no_root": "aucun taux ne rend la valeur actuelle nulle : TRI incalculable",
    "multiple_roots": "plusieurs taux annulent la valeur actuelle (flux de sens alternés) : TRI ambigu, non servi",
    "no_start": "valeur de départ absente de la série",
}





_IRR_LOG_BOUNDS = (-13.8, 13.8)

_IRR_SCAN_STEPS = 552


def _irr_npv(log_growth: float, start_value: float, flows, end_value: float, days: int) -> float:
    """Valeur actuelle, vue de l'investisseur, pour un facteur exp(log_growth) sur la période."""
    import math

    total = start_value - end_value * math.exp(-log_growth)
    for offset, amount in flows:
        total += amount * math.exp(-log_growth * offset / days)
    return total


def money_weighted_return(start_value: float, flows, end_value: float, days: int) -> dict:
    """Le rendement pondéré par l'argent d'une période, ou son refus par motif."""
    import math

    out = {"pct": None, "method": "irr", "annual_pct": None, "days": days, "reason": None}
    if days <= 0:
        return dict(out, method=None, reason="same_day")
    flows = [(max(0, min(days, int(offset))), float(amount)) for offset, amount in flows]
    low_bound, high_bound = _IRR_LOG_BOUNDS
    step = (high_bound - low_bound) / _IRR_SCAN_STEPS
    brackets = []
    previous = (low_bound, _irr_npv(low_bound, start_value, flows, end_value, days))
    for index in range(1, _IRR_SCAN_STEPS + 1):
        point = low_bound + index * step
        current = (point, _irr_npv(point, start_value, flows, end_value, days))
        if previous[1] == 0 or (previous[1] > 0) != (current[1] > 0):
            if not brackets or brackets[-1][1] != previous[0]:
                brackets.append((previous[0], current[0]))
        previous = current
    if not brackets:
        return dict(out, reason="no_root")
    if len(brackets) > 1:
        return dict(out, reason="multiple_roots")
    low, high = brackets[0]
    npv_low = _irr_npv(low, start_value, flows, end_value, days)
    if npv_low == 0:
        high = low
    for _ in range(200):
        if high - low < 1e-12:
            break
        middle = (low + high) / 2
        npv_middle = _irr_npv(middle, start_value, flows, end_value, days)
        if (npv_middle > 0) == (npv_low > 0):
            low, npv_low = middle, npv_middle
        else:
            high = middle
    log_growth = (low + high) / 2
    annual = (math.exp(log_growth * 365 / days) - 1) * 100 if days >= MWR_ANNUAL_FROM_DAYS else None
    return dict(out, pct=(math.exp(log_growth) - 1) * 100, annual_pct=annual)


def mwr_return(nav: dict[str, float], flows: dict[str, float], start_date: str,
               end_date: str) -> dict:
    """Rendement pondéré par l'argent du LIVRE entre deux séances de la série NAV."""
    import bisect

    start_value = nav.get(start_date)
    end_value = nav.get(end_date)
    days = (datetime.date.fromisoformat(end_date) - datetime.date.fromisoformat(start_date)).days
    if start_value is None or end_value is None or start_value <= 0:
        return {"pct": None, "method": None, "annual_pct": None, "days": days,
                "reason": "no_start", "net_flow": None}
    dates = sorted(nav)
    start = datetime.date.fromisoformat(start_date)
    dated = []
    for day, amount in sorted(flows.items()):
        if not start_date < day <= end_date:
            continue
        index = bisect.bisect_left(dates, day) - 1
        base = dates[index] if index >= 0 and dates[index] >= start_date else start_date
        dated.append(((datetime.date.fromisoformat(base) - start).days, amount))
    result = money_weighted_return(start_value, dated, end_value, days)
    result["net_flow"] = sum(amount for _, amount in dated)
    return result











RULINGS = SKILL / "references" / "bar-rulings.json"


def bar_rulings() -> dict:
    """Le registre des barres arbitrées, `{}` s'il manque ou est illisible."""
    try:
        return json.loads(RULINGS.read_text())
    except Exception:
        return {}


def bogus_bars_mask(conid, bar) -> set:
    """Dates (YYYY-MM-DD) dont l'extrême est JUGÉ FAUX pour ce (conid, granularité)."""
    out = set()
    reg = bar_rulings()
    for e in reg.get("bars", []):
        if e.get("verdict") != "bogus":
            continue
        if e.get("conid") not in (conid, "*"):
            continue
        if e.get("bar") not in (bar, "*", None):
            continue
        d = e.get("date")
        if d and d != "*":
            out.add(d)
    return out
