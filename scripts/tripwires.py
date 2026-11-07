#!/usr/bin/env python3
"""Évalue les niveaux pré-engagés de references/tripwires.json depuis le cache."""
from __future__ import annotations
import data_root
import json, sys, argparse, pathlib, datetime

import chart_ratios as cr
import bar_calendar
import price_cache
import book
import decision_schema
import instrument_categories
import instrument_store
import now as market_time
import refresh_observability as refresh_obs
import trailing
import manifest_groups as mg

HERE = pathlib.Path(__file__).resolve().parent
DEFAULT = data_root.tripwires_file()
POLICY = data_root.policy_file()


def theme_ids(path: pathlib.Path = POLICY) -> set[str]:
    """Les plafonds de thème décidés, lus sans importer `theme_caps` (qui importe ce module)."""
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return set()
    return {theme["id"] for theme in document.get("theme_caps") or []}
SNAPSHOTS = book.data_path() / "snapshots"
LEDGER = book.data_path() / "trades" / "ledger.jsonl"


HOLDINGS = None



WATCHLIST = None


WATCHLIST_MAX_AGE_DAYS = 14
MAX_AGE = {"1D": 4, "1W": 7, "1M": 35}
REQUIRED = {"id", "kind", "bar", "method", "added", "action"}



SCOPES = {"regime"}


def method_label(method) -> str:
    """Le libellé FRANÇAIS d'une méthode, pour le terminal."""
    if not isinstance(method, str):
        return str(method)
    return decision_schema.METHOD_LABELS.get(method, method)


def load_holding_records() -> dict[str, dict]:
    """Charge les seules fiches des lignes détenues dans le livre réconcilié."""
    latest = book.latest_snapshot(SNAPSHOTS)
    if latest is None:
        raise SystemExit("aucun snapshot de clôture : niveaux de plans inévaluables")
    holdings = book.reconciled_holdings(latest, LEDGER)
    records = instrument_store.records()


    residuals = book.sold_residuals(latest, holdings, records)
    return {symbol: records[symbol] for symbol in holdings
            if symbol in records and symbol not in residuals}


def candidate_symbols() -> set[str]:
    """Les fiches de SA LISTE qui portent des niveaux — le périmètre s'arrête là."""
    members = watchlist_members()
    symbols: set[str] = set()
    for sheet_path in sorted(instrument_store.SHEETS.glob("*.json")):
        sheet = json.loads(sheet_path.read_text(encoding="utf-8"))
        decision = sheet.get("decision") if isinstance(sheet.get("decision"), dict) else {}
        if not decision.get("levels"):
            continue






        if decision.get("status") in (decision_schema.STATUS_DISMISSED,
                                      decision_schema.STATUS_CLOSED):
            continue
        symbol = str(sheet.get("symbol") or sheet_path.stem).upper()
        if symbol in members:
            symbols.add(symbol)
    return symbols


def watchlist_members() -> set[str]:
    """L'appartenance à sa liste, lue du MIROIR — jamais d'une étiquette de fiche."""
    return instrument_store.watchlist_symbols(WATCHLIST)


def watchlist_age_days(today: datetime.date | None = None):
    """L'âge du miroir en jours, ou None s'il est absent ou ne se date pas."""
    source = WATCHLIST or instrument_store.WATCHLIST_TV
    if not source.exists():
        return None
    try:
        stamp = json.loads(source.read_text(encoding="utf-8")).get("updated")
    except (json.JSONDecodeError, OSError):
        return None
    if not isinstance(stamp, str):
        return None
    try:
        return ((today or datetime.date.today())
                - datetime.date.fromisoformat(stamp)).days
    except ValueError:
        return None


def load_candidate_records(uni, held=()) -> dict[str, dict]:
    """Charge les niveaux des fiches CANDIDAT, hors du livre réconcilié."""
    records = instrument_store.records()
    held_symbols = set(held)
    manifest = {symbol for symbol, entry in uni.items()
                if isinstance(entry, dict) and entry.get("conid")}
    return {symbol: records[symbol]
            for symbol in sorted(candidate_symbols())
            if symbol in records and symbol in manifest and symbol not in held_symbols}


def plan_levels(vh):
    """[(symbol, level dict)] — les niveaux structurés des plans (`plan.levels`)."""
    out = []
    for sym, entry in sorted(vh.items()):
        if sym.startswith("_") or not isinstance(entry, dict):
            continue
        plan = entry.get("plan") or {}
        for lv in plan.get("levels") or []:




            if "trail" in lv and isinstance(lv["trail"], dict):
                lv = dict(lv, trail=dict(lv["trail"]))
                lv["trail"].setdefault("since", plan.get("activated_on"))




            if "arm" in lv and isinstance(lv["arm"], dict):
                lv = dict(lv, arm=dict(lv["arm"]))
                lv["arm"].setdefault("since", plan.get("activated_on"))
            out.append((sym, lv))
    return out


def dead_clauses(uni, vh, today=None):
    """[(symbole, niveau, plancher)] — un étage de SORTIE fixe placé SOUS le"""
    by_sym: dict[str, list[dict]] = {}
    for sym, lv in plan_levels(vh):
        by_sym.setdefault(sym, []).append(lv)
    out = []
    for sym, levels in sorted(by_sym.items()):
        floors = [lv for lv in levels
                  if isinstance(lv.get("trail"), dict) and lv.get("op") == "<"]
        if not floors or sym not in uni:
            continue
        for lv in levels:
            px = lv.get("px")
            if lv.get("op") != "<" or not isinstance(px, (int, float)):
                continue
            for fl in floors:
                if fl.get("bar") != lv.get("bar"):
                    continue
                b, why = _bars(uni, sym, fl["bar"], today=today)
                if why:


                    continue
                try:
                    floor, _where = level_px(fl, b)
                except ValueError:
                    continue
                if float(px) < floor:
                    out.append((sym, lv, floor))
    return out


def mirrored_topic_ids(vh, tws):
    """{id: (symbole, opérateur, prix)} — entrées de topic qui DOUBLENT un plan."""
    fixes = {}
    for sym, lv in plan_levels(vh):
        if "px" not in lv:
            continue
        try:
            fixes[(sym, lv.get("bar"), lv.get("op"), float(lv["px"]))] = sym
        except (TypeError, ValueError):
            continue
    out = {}
    for tw in tws:
        if tw.get("kind") != "close":
            continue
        op = ">" if "above" in tw else "<" if "below" in tw else None
        if op is None:
            continue
        try:
            value = float(tw.get("above", tw.get("below")))
        except (TypeError, ValueError):
            continue
        key = (tw.get("symbol"), tw.get("bar"), op, value)
        if key in fixes:
            out[tw.get("id")] = (tw.get("symbol"), op, value)
    return out


def sma_value(b, bar, n):
    """(moyenne mobile sur n périodes RÉGLÉES, sa date, raison si impossible)."""
    return sma_of_rows(settled_series(b, bar), n)


def sma_of_rows(rows, n):
    """Le cœur de `sma_value` sur une série [(date, valeur)] DÉJÀ réglée."""
    if len(rows) < n:
        return None, None, (f"{len(rows)} période(s) réglée(s) en cache pour une SMA{n} — "
                            "fenêtre incomplète, pas de moyenne partielle")
    return sum(c for _, c in rows[-n:]) / n, rows[-1][0][:10], None


def _settled_bars(b, bar):
    """Les barres du cache réduites aux périodes RÉGLÉES, champs alignés."""
    return trailing.keep_periods(b, {ts for ts, _close in settled_series(b, bar)})


def level_px(lv, b):
    """(seuil effectif, son libellé) — LA seule loi qui résout un niveau."""
    if "sma" in lv:
        n = int(lv["sma"]["window"])
        sma, asof, why = sma_value(b, lv["bar"], n)
        if why:
            raise ValueError(why)
        return sma, f"{sma:.4g} [SMA{n} {lv['bar']} au {asof}]"
    if "trail" not in lv:
        return float(lv["px"]), f"{lv['px']}"
    tr = lv["trail"]
    px, raised_on = trailing.palier(_settled_bars(b, lv["bar"]), tr["seed"],
                                    tr.get("confirm", trailing.DEFAULT_CONFIRM), tr.get("since"))
    return px, f"{px:.4g} [palier mobile, seed {tr['seed']:.4g}, relevé le {raised_on}]"


def threshold_at(lv, b, stamp):
    """Le seuil d'un niveau pour la période RÉGLÉE qui finit à `stamp`, ou None."""
    if "trail" not in lv and "sma" not in lv:
        return float(lv["px"]) if isinstance(lv.get("px"), (int, float)) else None
    keep = [i for i, ts in enumerate(b.get("t", [])) if ts <= stamp]
    cut = dict(b)
    for key in ("t", "o", "h", "l", "c", "v"):
        if isinstance(b.get(key), list):
            cut[key] = [b[key][i] for i in keep]
    if lv.get("bar") == "1D":
        cut["settled_through"] = stamp[:10]
    else:
        cut.pop("settled_through", None)
    cut["fetched"] = stamp
    try:
        return level_px(lv, cut)[0]
    except (ValueError, IndexError, KeyError, TypeError):
        return None


def check_level(sym, lv, uni, today=None, ident=None):
    """Évalue un niveau de plan. Mêmes gardes que les topics : schéma nommé,"""
    ident = ident or f"plan {sym}"
    for f in ("op", "bar", "method", "action"):
        if f not in lv:
            return "UNVERIFIABLE", f"{ident}: champ « {f} » manquant dans plan.levels"



    has = [k for k in ("px", "trail", "sma") if k in lv]
    if len(has) != 1:
        return "UNVERIFIABLE", (f"{ident}: il faut EXACTEMENT un seuil px|trail|sma "
                                f"(trouvé : {has or 'aucun'})")
    if lv["op"] not in ("<", ">"):
        return "UNVERIFIABLE", f"{ident}: op « {lv['op']} » inconnu (<|>)"
    if lv["bar"] not in MAX_AGE:
        return "UNVERIFIABLE", f"{ident}: bar « {lv['bar']} » inconnu (1D|1W|1M)"
    if "px" in lv and not isinstance(lv["px"], (int, float)):
        return "UNVERIFIABLE", f"{ident}: px non numérique ({lv['px']!r})"
    if "trail" in lv:
        why = trailing.validate(lv["trail"])
        if why:
            return "UNVERIFIABLE", f"{ident}: {why}"
        if lv["op"] != "<":
            return "UNVERIFIABLE", (f"{ident}: `trail` n'a de sens qu'avec op « < » "
                                    "— un palier qui monte est un PLANCHER, pas une cible")
    if "sma" in lv:



        w = (lv["sma"] or {}).get("window")
        if not isinstance(w, int) or w < 2:
            return "UNVERIFIABLE", f"{ident}: sma.window doit être un entier ≥ 2 (trouvé {w!r})"
    if "arm" in lv:









        arm = lv["arm"]
        if (not isinstance(arm, dict) or arm.get("op") not in ("<", ">")
                or not isinstance(arm.get("px"), (int, float))):
            return "UNVERIFIABLE", (f"{ident}: `arm` doit être {{op: <|>, px: nombre}} "
                                    f"(trouvé {arm!r})")


        if not arm.get("since"):
            return "UNVERIFIABLE", (f"{ident}: `arm` sans `since` — un armement doit dater "
                                    "de la naissance du suivi (activated_on), sinon l'historique "
                                    "d'avant-plan le déclenche")
    if sym not in uni:
        return "UNVERIFIABLE", f"{ident}: {sym} absent de ratio-universe.json — ajouter le conid au manifeste"
    b, why = _bars(uni, sym, lv["bar"], today=today)
    if why:




        return "UNVERIFIABLE", f"{ident}: niveau(x) de plan invérifiable(s) — {why}"
    value, asof, partial = settled_close(b, lv["bar"])
    if value is None:
        return "UNVERIFIABLE", f"{ident}: aucune période finie en cache"
    if partial:
        asof += f" (partiel {partial[1]:.4g} au {partial[0][:10]})"




    arm_note = ""
    if "arm" in lv:
        op, apx, since = lv["arm"]["op"], lv["arm"]["px"], lv["arm"]["since"]
        fired = [ts[:10] for ts, c in settled_series(b, lv["bar"])
                 if ts[:10] >= since and (c > apx if op == ">" else c < apx)]
        if not fired:
            return "dormant", (f"{ident}: suiveur NON ARMÉ — aucune clôture {lv['bar']} "
                               f"{op} {apx} depuis {since} ; seuil "
                               f"{method_label(lv.get('method',''))} inerte "
                               f"tant que la cassure n'a pas eu lieu — {asof}")
        arm_note = f" [armé depuis {fired[0]}]"
    try:
        px, threshold = level_px(lv, b)
    except ValueError as e:
        return "UNVERIFIABLE", f"{ident}: {e}"
    hit = value < px if lv["op"] == "<" else value > px
    line = (f"{ident}: clôture {lv['bar']} = {value:.4g} vs {lv['op']} {threshold} "
            f"[{method_label(lv['method'])}]{arm_note} — {asof}")
    if hit:
        return "TRIGGERED", f"{line}\n      → {lv['action']}"
    settled = settled_series(b, lv["bar"])
    if len(settled) > 1:
        previous = settled[-2][1]
        previous_px = _previous_threshold(lv, b, settled[-1][0], px)
        previously_hit = previous_px is not None and (
            previous < previous_px if lv["op"] == "<" else previous > previous_px)
        if previously_hit:
            return "RETURNED", line
    return "armed", line


def _previous_threshold(lv, b, last_stamp, current_px):
    """Le seuil EN VIGUEUR à la période précédente, ou None s'il ne se calcule pas."""
    if "trail" not in lv and "sma" not in lv:
        return current_px
    keep = [i for i, ts in enumerate(b.get("t", [])) if ts < last_stamp]
    before = dict(b)
    for key in ("t", "o", "h", "l", "c", "v"):
        if isinstance(b.get(key), list):
            before[key] = [b[key][i] for i in keep]


    before.pop("settled_through", None)
    before["fetched"] = last_stamp
    try:
        return level_px(lv, before)[0]
    except (ValueError, IndexError):
        return None


def validate(tw, uni):
    """Raison du rejet, ou None si l'entrée est saine. Nomme toujours le champ."""
    ident = tw.get("id") or f"(entrée sans id : {json.dumps(tw, ensure_ascii=False)[:60]}…)"
    missing = REQUIRED - tw.keys()
    if missing:
        return f"{ident}: champ(s) manquant(s) {sorted(missing)}"
    if tw["kind"] not in ("close", "ratio", "sma", "book", "count"):
        return f"{tw['id']}: kind « {tw['kind']} » inconnu (close|ratio|sma|book|count)"
    if tw["kind"] == "count":
        legs = tw.get("legs")
        if (not isinstance(legs, list) or len(legs) < 2
                or not all(isinstance(leg, dict) and leg.get("num") and leg.get("den") for leg in legs)):
            return f"{tw['id']}: kind count exige au moins deux jambes {{num, den}} dans legs"
        if not isinstance(tw.get("leg_below"), (int, float)) or isinstance(tw.get("leg_below"), bool):
            return f"{tw['id']}: kind count exige leg_below, le seuil de chaque jambe (1,0 = sa moyenne)"


    if tw["kind"] == "book":
        if tw["bar"] != "1D":
            return f"{tw['id']}: kind book se lit sur la NAV quotidienne (bar 1D)"
    elif tw["bar"] not in ("1W", "1M"):
        return (f"{tw['id']}: bar « {tw['bar']} » inconnu (1W|1M) — "
                "1D est réservé aux niveaux explicites d'un plan détenu")
    thresholds = [k for k in ("above", "below") if k in tw]
    if len(thresholds) != 1:
        return (f"{tw['id']}: il faut EXACTEMENT un seuil above|below "
                f"(trouvé : {thresholds or 'aucun'}) — un double seuil serait évalué à moitié en silence")
    if not isinstance(tw[thresholds[0]], (int, float)):
        return f"{tw['id']}: seuil {thresholds[0]} non numérique ({tw[thresholds[0]]!r})"
    syms = tripwire_symbols(tw)
    if None in syms:
        need = "num et den" if tw["kind"] == "ratio" else "symbol"
        return f"{tw['id']}: kind {tw['kind']} exige {need}"
    if tw["kind"] in ("sma", "count") or (tw["kind"] == "ratio" and "window" in tw):
        w = tw.get("window")
        if isinstance(w, bool) or not isinstance(w, int) or w < 2:
            return f"{tw['id']}: kind {tw['kind']} exige window entier ≥ 2 (trouvé : {w!r})"
    if "release_closes" in tw:
        n = tw["release_closes"]
        if isinstance(n, bool) or not isinstance(n, int) or n < 1:
            return f"{tw['id']}: release_closes exige un entier ≥ 1 (trouvé : {n!r})"
        if tw["kind"] not in ("close", "ratio", "count"):
            return f"{tw['id']}: release_closes ne vaut que pour les kinds close, ratio et count"
    for s in syms:
        if s not in uni:
            return f"{tw['id']}: {s} absent de ratio-universe.json"



    if "scope" in tw and tw["scope"] not in SCOPES:
        return f"{tw['id']}: scope « {tw['scope']} » inconnu ({'|'.join(sorted(SCOPES))})"
    if "exposure" in tw:
        if tw.get("scope") != "regime":
            return f"{tw['id']}: exposure n'a de sens qu'avec scope « regime »"
        codes = tw["exposure"]
        if not isinstance(codes, list) or not codes:
            return f"{tw['id']}: exposure exige une liste non vide de catégories"
        unknown = [c for c in codes if c not in instrument_categories.CATEGORIES]
        if unknown:
            return f"{tw['id']}: exposure porte des catégories inconnues {unknown}"


    if "exposure_theme" in tw:
        if tw.get("scope") != "regime":
            return f"{tw['id']}: exposure_theme n'a de sens qu'avec scope « regime »"
        if "exposure" in tw:
            return f"{tw['id']}: exposure et exposure_theme s'excluent — une seule mesure"
        known = theme_ids()
        if tw["exposure_theme"] not in known:
            return f"{tw['id']}: exposure_theme « {tw['exposure_theme']} » absent de portfolio-policy.json"




    if "closes_entries" in tw:
        if not isinstance(tw["closes_entries"], bool):
            return f"{tw['id']}: closes_entries doit valoir true ou false ({tw['closes_entries']!r})"
        if tw.get("scope") != "regime":
            return f"{tw['id']}: closes_entries n'a de sens qu'avec scope « regime »"



    if tw.get("scope") == "regime":
        if not isinstance(tw.get("label"), str) or not tw["label"].strip():
            return f"{tw['id']}: une alerte de régime exige un label lisible"


    if "review_by" in tw and not _iso_day(tw["review_by"]):
        return f"{tw['id']}: review_by doit être une date AAAA-MM-JJ ({tw['review_by']!r})"
    for prose in ("exposure_note", "meaning"):
        if prose in tw and (not isinstance(tw[prose], str) or not tw[prose].strip()):
            return f"{tw['id']}: {prose} doit être un texte non vide"
    if "display" in tw:
        disp = tw["display"]
        if (not isinstance(disp, dict) or set(disp) - {"factor", "unit"}
                or not isinstance(disp.get("factor", 1), (int, float))
                or not isinstance(disp.get("unit", ""), str)):
            return f"{tw['id']}: display attend {{factor: nombre, unit: texte}}"
    return None


def tripwire_symbols(tw):
    """Les séries qu'un tripwire lit : aucune pour le livre, toutes les jambes d'un count."""
    kind = tw.get("kind")
    if kind == "book":
        return []
    if kind == "ratio":
        return [tw.get("num"), tw.get("den")]
    if kind == "count":
        return [leg.get(side) for leg in tw.get("legs") or [] for side in ("num", "den")]
    return [tw.get("symbol")]


def count_legs(tw):
    """Chaque jambe d'un kind count, en kind ratio évaluable par `check`."""
    shared = {key: tw[key] for key in ("bar", "window", "method", "added", "action", "release_closes")
              if key in tw}
    return [{**shared, "id": f"{tw['id']}:{leg['num']}/{leg['den']}", "kind": "ratio",
             "num": leg["num"], "den": leg["den"], "below": tw["leg_below"]}
            for leg in tw["legs"]]


def _bars(uni, symbol, bar, today=None):
    """(bars dict, problème ou None) — cache lu par conid via le manifeste."""
    b = (price_cache.read_cache(uni[symbol]["conid"]) or {}).get("bars", {}).get(bar)
    if not b:
        return None, f"cache {bar} absent pour {symbol} (conid {uni[symbol]['conid']})"
    if bar == "1D" and not b.get("settled_through"):
        return None, (f"cache 1D de {symbol} sans borne de clôture réglée — "
                      "impossible de distinguer une barre finale d'un instantané intrajournalier. "
                      "Tirer via refresh_close.py.")
    today = today or datetime.date.today()
    age = (today - datetime.date.fromisoformat(b["fetched"])).days
    if age > MAX_AGE[bar]:
        return None, f"cache {bar} de {symbol} périmé ({age} j) — tirer via --stale"



    manque = settlement_gap(b, bar, week_ends_sunday=sunday_week_end(uni, symbol))
    if manque:
        p = "clôture" + ("s" if manque > 1 else "")
        return None, (f"cache {bar} de {symbol} EN RETARD de {manque} {p} réglée(s) — "
                      f"le seuil serait évalué sur une période périmée "
                      f"(âge {age} j, sous le seuil de {MAX_AGE[bar]} j : "
                      f"l'ancienne garde se taisait). Tirer via --stale.")
    return b, None


def sunday_week_end(uni, symbol):
    """Cette série clôt-elle sa semaine le DIMANCHE (actif 24/7) ?"""
    return mg.crypto_venue(uni.get(symbol)) is not None


def _period_end(ts, bar, week_ends_sunday=False):
    """Dernier jour : date (1D), vendredi (1W) ou fin de mois (1M)."""
    return bar_calendar.period_end(ts, bar, week_ends_sunday)

def settlement_gap(b, bar, aujourdhui=None, week_ends_sunday=False):
    """Combien de clôtures RÉGLÉES manquent entre la dernière du cache et aujourd'hui."""
    if bar == "1D":
        lag = settlement_lag(b, bar, week_ends_sunday=week_ends_sunday)
        return lag[0] if lag else 0
    auj = aujourdhui or datetime.date.today()
    settled = settled_series(b, bar)
    if not settled:
        return 0
    fin = _period_end(settled[-1][0], bar, week_ends_sunday)
    n = 0
    while True:
        if bar == "1W":
            suivante = fin + datetime.timedelta(days=7)
        else:
            j = fin + datetime.timedelta(days=1)
            suivante = _period_end(j.isoformat(), bar, week_ends_sunday)

        if suivante >= auj:
            return n
        fin = suivante
        n += 1


def _periods(b, bar):
    """[(ts, close)] — UNE barre par période (la plus fraîche du cache), ordre"""
    per = {}
    for ts, c in zip(b["t"], b["c"]):
        per[bar_calendar.bar_period(ts, bar)] = (ts, c)
    return sorted(per.values())


def as_of_clock(at=None):
    """(date locale, instant UTC) d'une horloge INJECTÉE, ou ``(None, None)``."""
    if at is None:
        return None, None
    if not isinstance(at, datetime.datetime):
        raise TypeError(
            "horloge injectée : un datetime (naïf lu comme UTC), pas une date "
            "nue — « ce jour-là » ne dit pas quelle clôture US est passée")
    current = refresh_obs.normalize_time(at)
    return current.astimezone().date(), current


def settled_series(b, bar, *, today=None, at=None):
    """[(ts, close)] des périodes FINIES — socle commun de settled_close (qui"""
    if bar == "1D":
        boundary = b.get("settled_through")
        if not boundary:
            return []
        due = market_time.last_completed_us_session(as_of_clock(at)[1])
        limit = min(datetime.date.fromisoformat(boundary), due)
        return [(ts, c) for ts, c in _periods(b, bar)
                if datetime.date.fromisoformat(ts[:10]) <= limit
                and market_time.is_us_session(datetime.date.fromisoformat(ts[:10]))]
    return bar_calendar.completed_series(b, bar, as_of=today or as_of_clock(at)[0]
                               or datetime.date.today())

def period_due(bar, today=None, now=None, week_ends_sunday=False):
    """La dernière période qui DEVRAIT être réglée aujourd'hui — clé `bar_period`."""
    if bar == "1D":
        due = market_time.last_completed_us_session(as_of_clock(now)[1])
        return due.isoformat(), due
    today = today or as_of_clock(now)[0] or datetime.date.today()
    d = today
    for _ in range(400):
        fin = _period_end(d.isoformat(), bar, week_ends_sunday)
        if fin < today:
            return bar_calendar.bar_period(d.isoformat(), bar), fin
        d = fin - datetime.timedelta(days=7) if bar == "1W" else \
            datetime.date(d.year, d.month, 1) - datetime.timedelta(days=1)
    raise RuntimeError(
        f"periode_due({bar}, {today}) ne converge pas — calendrier cassé")


def settlement_lag(b, bar, today=None, now=None, week_ends_sunday=False):
    """(nb de périodes de retard, période due, période en cache) ou None si à jour."""
    due, fin = period_due(bar, today, now, week_ends_sunday=week_ends_sunday)
    settled = settled_series(b, bar, today=today, at=now)
    if not settled:
        return None
    have = bar_calendar.bar_period(settled[-1][0], bar)
    if have >= due:
        return None
    if bar == "1D":
        manquantes = 0
        day = datetime.date.fromisoformat(have) + datetime.timedelta(days=1)
        while day <= fin:
            if market_time.is_us_session(day):
                manquantes += 1
            day += datetime.timedelta(days=1)
        return manquantes, due, have







    manquantes, d = 0, fin
    while manquantes < 60 and bar_calendar.bar_period(d.isoformat(), bar) > have:
        manquantes += 1
        d = (d - datetime.timedelta(days=7) if bar == "1W"
             else datetime.date(d.year, d.month, 1) - datetime.timedelta(days=1))
    return manquantes, due, have


def retards(uni, vh, tws):
    """[(symbol, bar, n)] — les séries qui portent un niveau ARMÉ et à qui il"""
    needed = {
        (s, lv.get("bar"))
        for s, lv in plan_levels(vh)
        if isinstance(lv, dict) and lv.get("bar") in MAX_AGE
    }
    for t in tws:
        if t.get("bar") == "1D":
            continue
        for s in tripwire_symbols(t):
            if s:
                needed.add((s, t.get("bar")))
    out = []
    for s, bar in sorted(needed):
        if s not in uni or bar not in MAX_AGE:
            continue
        b = (price_cache.read_cache(uni[s]["conid"]) or {}).get("bars", {}).get(bar)
        if not b:
            continue
        r = settlement_lag(b, bar, week_ends_sunday=sunday_week_end(uni, s))
        if r:
            out.append((s, bar, r[0]))
    return out


def settled_close(b, bar):
    """(close de la dernière période FINIE, sa date, partiel ou None)."""
    rows = _periods(b, bar)
    settled = settled_series(b, bar)
    partial = rows[-1] if rows and rows[-1] not in settled else None
    if not settled:
        return None, None, partial
    ts, c = settled[-1]
    return c, ts[:10], partial


def cache_price(b, aujourdhui=None):
    """(dernier prix du cache, date du TIRAGE, âge en jours) — le pendant de"""
    if not b or not b.get("c"):
        return None, None, None
    px = b["c"][-1]
    f = b.get("fetched")
    if not f:
        return px, None, None
    age = ((aujourdhui or datetime.date.today())
           - datetime.date.fromisoformat(f[:10])).days
    return px, f[:10], age


def price_with_age(px, fetched, age, decimales=2):
    """L'étiquette d'un prix de cache — une seule formulation, partout."""
    if px is None:
        return "prix indisponible"
    if fetched is None:
        return f"{px:.{decimales}f} (cache, tirage NON DATÉ)"
    if age == 0:
        return f"{px:.{decimales}f} (cache du jour)"
    return (f"{px:.{decimales}f} (cache du {fetched}, {age} j)"
            + ("  ⚠ PÉRIMÉ" if age >= 2 else ""))


def _verdict(value, tw):
    if "below" in tw:
        return value < tw["below"], f"< {tw['below']}"
    return value > tw["above"], f"> {tw['above']}"


def _condition(tw):
    """La condition ÉCRITE du tripwire, sans valeur : « > 37.35 », « ÷SMA10 1M »."""
    if "below" in tw:
        return f"< {tw['below']}"
    if "above" in tw:
        return f"> {tw['above']}"
    if "window" in tw:
        return f"÷SMA{tw['window']} {tw['bar']}"
    return tw["kind"]


def topic_value(tw, uni):
    """(value, asof, label, why) d'un tripwire de topic — la valeur COURANTE,"""
    if tw["kind"] == "book":
        drawdown = book.nav_drawdown()
        if drawdown is None:
            return None, None, None, f"{tw['id']}: aucune NAV quotidienne (data/flex/navdaily-*.csv)"
        return (drawdown["pct"], f"NAV du {drawdown['last_on']}, sommet du {drawdown['peak_on']}",
                "LIVRE baisse depuis le sommet %", None)
    if tw["kind"] == "count":
        states = []
        for leg in count_legs(tw):
            status, line = check(leg, uni)
            if status == "UNVERIFIABLE":
                return None, None, None, f"{tw['id']}: jambe {leg['num']}/{leg['den']} — {line}"
            states.append((leg, status == "TRIGGERED", line))
        rows, _ = ratio_rows(states[0][0], uni)
        week = f"semaine finie {rows[-1][0]}" if rows else "semaine finie inconnue"
        asof = ", ".join(f"{leg['num']}/{leg['den']} {'sous' if on else 'au-dessus de'} sa SMA{tw['window']}"
                         for leg, on, _ in states)
        label = "·".join(f"{leg['num']}/{leg['den']}" for leg, _, _ in states)
        return (float(sum(on for _, on, _ in states)), f"{week} — {asof}",
                f"{label} sous SMA{tw['window']} {tw['bar']}", None)
    if tw["kind"] == "close":
        b, why = _bars(uni, tw["symbol"], tw["bar"])
        if why:
            return None, None, None, (f"{tw['id']}: {_condition(tw)} "
                                      f"[{method_label(tw['method'])}] — {why}")
        value, asof, partial = settled_close(b, tw["bar"])
        if value is None:
            return None, None, None, f"{tw['id']}: aucune période finie en cache"
        if partial:
            asof += f" (partiel {partial[1]:.4g} au {partial[0][:10]})"
        return value, asof, f"{tw['symbol']} clôture {tw['bar']}", None
    if tw["kind"] == "sma":
        b, why = _bars(uni, tw["symbol"], tw["bar"])
        if why:
            return None, None, None, (f"{tw['id']}: {_condition(tw)} "
                                      f"[{method_label(tw['method'])}] — {why}")
        n = tw["window"]
        sma, asof, why = sma_value(b, tw["bar"], n)
        if why:
            return None, None, None, f"{tw['id']}: {why}"
        close = settled_series(b, tw["bar"])[-1][1]
        _, _, partial = settled_close(b, tw["bar"])
        ctx = f" (partiel {partial[1]:.4g} au {partial[0][:10]})" if partial else ""



        return (close / sma, f"{asof} — clôture {close:.4g} / SMA{n} {sma:.4g}{ctx}",
                f"{tw['symbol']}÷SMA{n} {tw['bar']}", None)
    if "window" in tw:
        rows, why = ratio_rows(tw, uni)
        if why:
            return None, None, None, f"{tw['id']}: {why}"
        n = tw["window"]
        sma, asof, why = sma_of_rows(rows, n)
        if why:
            return None, None, None, f"{tw['id']}: {why}"
        return (rows[-1][1] / sma, f"{asof} — ratio {rows[-1][1]:.4g} / SMA{n} {sma:.4g}",
                f"{tw['num']}/{tw['den']}÷SMA{n} {tw['bar']}", None)
    num, why = _bars(uni, tw["num"], tw["bar"])
    if not why:
        den, why = _bars(uni, tw["den"], tw["bar"])
    if why:
        return None, None, None, f"{tw['id']}: {why}"
    if tw["bar"] == "1M":
        nc, n_last = bar_calendar.month_closes(num)
        dc, d_last = bar_calendar.month_closes(den)
        if not nc or not dc:
            return None, None, None, f"{tw['id']}: pas de mois complet en cache"
        return (nc[-1] / dc[-1], f"dernier mois complet (partiel {n_last / d_last:.4g})",
                f"{tw['num']}/{tw['den']} {tw['bar']}", None)








    ns = {bar_calendar.bar_period(ts, "1W"): c for ts, c in settled_series(num, "1W")}
    ds = {bar_calendar.bar_period(ts, "1W"): c for ts, c in settled_series(den, "1W")}
    common = sorted(set(ns) & set(ds))
    if not common:
        return None, None, None, f"{tw['id']}: pas de semaine finie commune en cache"
    k = common[-1]
    partial = num["c"][-1] / den["c"][-1]
    return (ns[k] / ds[k], f"dernière semaine finie {k} (partiel {partial:.4g})",
            f"{tw['num']}/{tw['den']} {tw['bar']}", None)


def recent_values(tw, uni, n):
    """Les `n` dernières valeurs RÉGLÉES d'un tripwire close ou ratio, de la plus"""
    bar = tw["bar"]
    if tw["kind"] == "close":
        b, why = _bars(uni, tw["symbol"], bar)
        return [] if why else [c for _, c in settled_series(b, bar)[-n:]]
    rows, why = ratio_rows(tw, uni)
    if why:
        return []
    if "window" not in tw:
        return [v for _, v in rows[-n:]]

    w = tw["window"]
    return [rows[i][1] / sma_of_rows(rows[:i + 1], w)[0]
            for i in range(max(w - 1, len(rows) - n), len(rows))]


def ratio_rows(tw, uni):
    """([(période, num/den)] des périodes RÉGLÉES COMMUNES aux deux jambes, raison)."""
    bar = tw["bar"]
    num, why = _bars(uni, tw["num"], bar)
    den, why2 = _bars(uni, tw["den"], bar) if not why else (None, why)
    if why or why2:
        return [], why or why2
    ns = {bar_calendar.bar_period(ts, bar): c for ts, c in settled_series(num, bar)}
    ds = {bar_calendar.bar_period(ts, bar): c for ts, c in settled_series(den, bar)}
    common = sorted(set(ns) & set(ds))
    if not common:
        return [], f"pas de période {bar} finie commune à {tw['num']} et {tw['den']} en cache"
    return [(k, ns[k] / ds[k]) for k in common], None


def _iso_day(value) -> datetime.date | None:
    try:
        return datetime.date.fromisoformat(value) if isinstance(value, str) else None
    except ValueError:
        return None


def expired_on(tw, today: datetime.date | None = None):
    """La date `review_by` dépassée d'un capteur, sinon False."""
    day = _iso_day(tw.get("review_by"))
    if day is None:
        return False
    return day if day < (today or datetime.date.today()) else False


def check(tw, uni):
    """(status, ligne). status ∈ armed | TRIGGERED | UNVERIFIABLE."""
    why = validate(tw, uni)
    if why:
        return "UNVERIFIABLE", why
    value, asof, label, why = topic_value(tw, uni)
    if why:
        return "UNVERIFIABLE", why
    hit, cond = _verdict(value, tw)

    release = 1 if tw["kind"] == "count" else tw.get("release_closes", 1)
    if release > 1:
        cond += f", levée après {release} clôtures consécutives"
        recent = recent_values(tw, uni, release)
        hit = any(_verdict(v, tw)[0] for v in recent)
        asof += " ; dernières " + ", ".join(f"{v:.4g}" for v in recent)
    line = (f"{label} = {value:.4g} vs {cond} [{method_label(tw['method'])}] — {asof}")
    if hit:
        return "TRIGGERED", f"{tw['id']}: {line}\n      → {tw['action']}"
    return "armed", f"{tw['id']}: {line}"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--file", default=str(DEFAULT))
    ap.add_argument("--brief", action="store_true",
                    help="ne montrer que ce qui n'est PAS simplement armé (déclenché, inévaluable) "
                         "+ le compte des armés — le détail se lit sur la carte des distances "
                         "(chart_levels.py), qui est la sortie par défaut depuis le 2026-07-21")
    a = ap.parse_args()



    topics = pathlib.Path(a.file)
    if topics.exists():
        tws = json.loads(topics.read_text(encoding="utf-8"))["tripwires"]
    else:
        print(f"aucun niveau de topic : {topics.name} absent — seuls les plans des fiches sont évalués")
        tws = []
    uni, _ = cr.load_universe()
    if HOLDINGS is None:
        vh = load_holding_records()
    else:
        fixture = pathlib.Path(HOLDINGS)
        vh = json.loads(fixture.read_text()) if fixture.exists() else {}



    cands = load_candidate_records(uni, held=vh)



    mirror_age = watchlist_age_days()
    if mirror_age is not None and mirror_age > WATCHLIST_MAX_AGE_DAYS:
        print(f"  ⚠ miroir TradingView vieux de {mirror_age} j — la veille suit une "
              f"intention qui n'a pas été réaffirmée ; réimporter la liste "
              f"(`tv_watchlist.py --import`)")
    watched = {**cands, **vh}
    marks = {"armed": "·", "TRIGGERED": "⚑⚑", "RETURNED": "↩", "UNVERIFIABLE": "⛔", "dormant": "○"}
    rc, armed, dormant, triggered = 0, 0, 0, 0

    def emit(status, line, header=None):
        """Un armé ne s'imprime qu'en mode complet : en --brief il se COMPTE."""
        nonlocal rc, armed, dormant, triggered
        if status in ("armed", "dormant"):
            if status == "armed":
                armed += 1
            else:
                dormant += 1
            if a.brief:
                return
        if header and header[0]:
            print(header[1]); header[0] = False
        print(f"  {marks[status]} [{status}] {line}")
        if status == "TRIGGERED":
            triggered += 1
        if status == "UNVERIFIABLE":
            rc = 1




    tard = retards(uni, watched, tws)
    if tard:
        rc = 1
        n = len({s for s, _, _ in tard})
        print(f"  ⛔ RETARD DE CLÔTURE — {n} série(s) portant un niveau armé n'ont pas "
              f"leur dernière clôture réglée ; leurs distances sont FAUSSES.")
        for bar in ("1D", "1W", "1M"):
            grp = sorted({s for s, b, _ in tard if b == bar})
            if grp:
                due = period_due(bar)[0]
                print(f"     {bar} due {due} — {len(grp)} : " + ", ".join(grp[:12])
                      + ("…" if len(grp) > 12 else ""))
        print("     → python3 scripts/refresh_close.py "
              "(ou --only SYM,SYM) ; une barre tirée EN COURS de période reste partielle "
              "jusqu'à un tirage postérieur à la clôture.")





    cand_levels = plan_levels(cands)
    lvls = plan_levels(vh)
    mirrors = mirrored_topic_ids(watched, tws)
    candidate_syms = set(cands)



    h = [True, "  — veille (fiches non détenues, enveloppe plan.levels) —"]
    for sym, lv in cand_levels:
        emit(*check_level(sym, lv, uni, ident=f"veille {sym}"), header=h)
    h = [True, "  — niveaux de plans (lignes détenues, enveloppe plan.levels) —"]
    for sym, lv in lvls:
        emit(*check_level(sym, lv, uni), header=h)





    mortes = dead_clauses(uni, vh)
    if mortes:
        print("  ⚠ CLAUSE MORTE — un étage de SORTIE fixe placé SOUS le plancher mobile "
              f"du même plan ne peut plus sonner avant lui  ({len(mortes)})")
        for sym, lv, floor in mortes:
            print(f"     {sym:6s} `{lv['op']} {lv['px']:g}` ({lv['bar']}) couvert par le "
                  f"plancher mobile {floor:.4g} — retirer la clause ou la déplacer")
    h = [True, "  — topics (registre) —"]
    for tw in tws:


        if tw.get("id") in mirrors:
            if not a.brief:
                sym, op, px = mirrors[tw["id"]]
                source = ("plan veille" if sym in candidate_syms and sym not in vh
                          else "plan")
                if h[0]:
                    print(h[1])
                    h[0] = False
                print(f"  ↔ [miroir] {tw['id']}: même seuil que le {source} {sym} "
                      f"({op} {px:g}) — non recompté, non réévalué")
            continue
        emit(*check(tw, uni), header=h)


    echus = [(tw["id"], day) for tw in tws if (day := expired_on(tw))]
    if echus:
        print(f"  ⚠ ÉCHU — capteur(s) à réaffirmer, review_by dépassé  ({len(echus)})")
        for ident, day in echus:
            print(f"     {ident} échu le {day.isoformat()} — reporter review_by ou retirer le capteur")
    if a.brief:
        note = f"  {armed} niveau(x) ARMÉ(S), "
        note += f"{triggered} franchi(s)" if triggered else "aucun franchi"
        if dormant:
            note += f" · {dormant} DORMANT(S) (suiveur non armé, inerte)"
        print(note + " — détail et proximité : carte des distances (chart_levels.py)")
    if not tws and not lvls and not cand_levels:
        print("  aucun tripwire posé.")
    print("\n  Un tripwire déclenché n'est pas un ordre : il relève son topic ;")
    print("  la décision passe par le plan. Ajouter/retirer = references/tripwires.json.")
    if rc:
        sys.exit(rc)


if __name__ == "__main__":
    main()
