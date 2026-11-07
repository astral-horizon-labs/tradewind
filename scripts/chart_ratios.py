#!/usr/bin/env python3
"""Force relative (ratios) base/benchmarks, AVEC CACHE DE PRIX incrémental."""
from __future__ import annotations
import data_root
import json, sys, argparse, pathlib, datetime, statistics
from number_format import fr_number
import atomic_file
import bar_calendar
import fx_history
import manifest_groups as mg
import price_cache

HERE = pathlib.Path(__file__).resolve().parent
SKILL = HERE.parent
UNIVERSE_FILE = data_root.universe_file()

BARS = {"1W": ("ONE_WEEK", "period=ONE_YEAR", 5),
        "1M": ("ONE_MONTH", "step_count=37", 25)}
WINDOWS = {
    "1W": [("1 an", 52), ("6 mois", 26), ("3 mois", 13), ("8 sem", 8), ("4 sem", 4)],
    "1M": [("3 ans", 36), ("2 ans", 24), ("1 an", 12), ("6 mois", 6), ("3 mois", 3)],
}
GROUP_COLOR = {"health": "#1D9E75", "tech": "#2a78d6", "market": "#888780", "sectors": "#eb6834", "held": "#7f77dd", "regions": "#c98500"}
LINE_PALETTE = ["#0F6E56", "#1D9E75", "#3DB78D", "#2a78d6", "#4a3aa7", "#eb6834", "#eda100",
                "#e34948", "#888780", "#5DCAA5", "#85B7EB", "#e87ba4", "#9FE1CB", "#c98500",
                "#199e70", "#d55181", "#7f77dd", "#b4b2a9", "#378ADD", "#639922"]


def today():
    return datetime.date.today()


def load_universe():
    d = json.loads(UNIVERSE_FILE.read_text())
    return d["instruments"], d.get("base_default", "SBIO")


def fr(v, dec=1):
    return fr_number(v, dec, signed=True, grouped=False)




def cmd_universe(uni, base):
    print(f"# base par défaut : {base}   |   cache : {price_cache.CACHE_DIR}")
    for sym, m in uni.items():
        cov = []
        c = price_cache.read_cache(m["conid"])
        for bar in BARS:
            if c and bar in c.get("bars", {}):
                b = c["bars"][bar]
                cov.append(f"{bar}:{b['t'][-1][:10]}({len(b['t'])})")
            else:
                cov.append(f"{bar}:—")
        print(f"{sym:6} {m['conid']:<12} [{mg.label(m['group']):8}] {m['label']:34} {'  '.join(cov)}")


def cmd_stale(uni, bar, max_age):
    step, hint, default_age = BARS[bar]
    max_age = max_age if max_age is not None else default_age
    todo = []
    for sym, m in uni.items():
        c = price_cache.read_cache(m["conid"])
        b = (c or {}).get("bars", {}).get(bar)
        if not b:
            todo.append((sym, m, "absent"))
        else:
            age = (today() - datetime.date.fromisoformat(b["fetched"])).days
            if age > max_age:
                todo.append((sym, m, f"périmé {age}j"))
    if not todo:
        print(f"cache {bar} À JOUR — rien à tirer ({len(uni)} instruments, âge max {max_age}j).")
        return
    print(f"# À TIRER en {bar} ({len(todo)}/{len(uni)}) — connecteur get_price_history STK step={step} {hint} outside_rth=false")
    for sym, m, why in todo:
        print(f"{sym:6} conid={m['conid']:<12} ({why})")
    print(f"# puis écrire {{\"series\": {{\"SYM\": {{\"t\":[...], \"c\":[...]}}}}}} et : chart_ratios.py --ingest <f> --bar {bar}")


def ingest_series(series, bar, conids):
    """Verse des barres au cache, garde-fou anti-mismap compris."""
    n, skipped, rejected = 0, [], []
    stamp = today().isoformat()
    for sym, sc in series.items():
        if sym not in conids:
            skipped.append(sym)
            continue
        conid = conids[sym]



        obj = price_cache.read_cache(conid) or {"conid": conid, "symbol": sym, "bars": {}}
        other = "1M" if bar == "1W" else "1W"
        ob = obj["bars"].get(other)
        if ob and sc["c"] and ob["c"]:
            ref, got = ob["c"][-1], sc["c"][-1]
            if ref and abs(got - ref) / ref > 0.08:
                rejected.append(f"{sym} ({bar} finit {got}, mais {other} finit {ref} — écart {abs(got-ref)/ref:.0%})")
                continue


        import market_source
        merged = price_cache.merge_bars(obj["bars"].get(bar), sc["t"], sc["c"], bar,
                            sc.get("h"), sc.get("l"), sc.get("o"),
                            primary=market_source.primary(conid))
        merged["fetched"] = stamp
        obj["bars"][bar] = merged
        obj["symbol"] = sym
        price_cache.write_cache(conid, obj)
        n += 1
    return n, skipped, rejected, stamp


def print_rejected(rejected):
    if rejected:
        print("⛔ REJETÉS par le garde-fou (dernière clôture incohérente vs l'autre granularité) :")
        for r in rejected:
            print(f"   {r}")


def cmd_ingest(path, bar, uni):
    data = json.loads(pathlib.Path(path).read_text())
    series = data.get("series", data)
    n, skipped, rejected, stamp = ingest_series(
        series, bar, {sym: m["conid"] for sym, m in uni.items()})
    print(f"ingéré {n} instrument(s) en {bar} (fetched={stamp}).")
    if skipped:
        print(f"⚠ ignorés (absents du manifeste) : {', '.join(skipped)}")
    print_rejected(rejected)





def in_groups(m, groups):
    """Appartenance MULTI-GROUPE : le champ optionnel `groups` (liste) l'emporte"""
    if not groups:
        return True
    return bool(mg.of(m) & groups)


def series_momentum(bar):
    """{m12, m6, m3, trend} d'UNE série mensuelle — la loi du momentum, en un"""
    closes, last = bar_calendar.month_closes(bar)
    keys = bar_calendar.month_keys(bar)

    def mom(k):
        return bar_calendar.calendar_return(keys, closes, k)

    gaps = [k for k in (3, 6, 12) if len(closes) > k and mom(k) is None]
    sma10 = sum(closes[-10:]) / 10 if len(closes) >= 10 else None












    trend = None if sma10 is None else ("AU-DESSUS" if last > sma10 else "SOUS")
    trend_settled = (None if sma10 is None
                     else ("AU-DESSUS" if closes[-1] > sma10 else "SOUS"))
    return {"m12": mom(12), "m6": mom(6), "m3": mom(3),
            "gap": bool(gaps),
            "trend": trend,
            "trend_settled": trend_settled,
            "trend_split": bool(trend and trend_settled and trend != trend_settled)}


def momentum_rows(uni, group, as_of=None):
    """(rows, stale) — le calcul du momentum, SANS affichage. Extrait de"""


    groups = set(mg.parse_list(group)) if group else None
    rows, stale = [], []
    for sym, m in uni.items():
        if not in_groups(m, groups):
            continue
        c = price_cache.read_cache(m["conid"])
        b = (c or {}).get("bars", {}).get("1M")
        if not b:
            stale.append(sym); continue
        b = bar_calendar.bars_through(b, as_of)
        if not b:
            stale.append(sym); continue
        rows.append({"sym": sym, "label": m["label"], "group": m["group"],
                     "subsector": m.get("subsector"),
                     **series_momentum(b), "fetched": b["fetched"]})


    score_rows(rows)
    return rows, stale


def score_rows(rows):
    """Pose `score` (rang composite) et `accel` sur chaque ligne ; renvoie les"""
    ranked = [r for r in rows if all(r[k] is not None for k in ("m12", "m6", "m3"))]
    ranks = {r["sym"]: [] for r in ranked}
    for k in ("m12", "m6", "m3"):
        for i, r in enumerate(sorted(ranked, key=lambda z: -z[k]), 1):
            ranks[r["sym"]].append(i)
    for r in rows:
        r["score"] = sum(ranks[r["sym"]]) / len(ranks[r["sym"]]) if r["sym"] in ranks else None



        r["accel"] = (ranks[r["sym"]][0] - ranks[r["sym"]][2]) if r["sym"] in ranks else None
    return ranked


def cmd_momentum(uni, group, top=None):
    rows, stale = momentum_rows(uni, group)
    if not rows:
        sys.exit("cache 1M vide pour ce périmètre — remplir d'abord (--stale --bar 1M).")




    ranked = score_rows(rows)
    oldest = min(r["fetched"] for r in rows)
    scope = (f"groupe={', '.join(mg.label(g) for g in mg.parse_list(group))}"
             if group else f"{len(rows)} instruments")
    print(f"MOMENTUM — {scope} — mensuel (mois complets, mois courant sauté) — cache du {oldest}")
    print("12-1 = Jegadeesh-Titman ; composite = rang moyen 12-1/6-1/3-1 (1 = plus fort) ; SMA10M = filtre Faber\n"
          "  ATTENTION deux horloges : 12-1/6-1/3-1 sur mois COMPLETS, SMA10M sur le DERNIER PRIX "
          "(mois partiel).\n  « ~ » = les deux lectures divergent — la clôture réglée dit l'inverse "
          "(convention de tripwires.py).")
    print("accél = rangs gagnés du 12-1 au 3-1 (+ = démarre, − = s'essouffle ; le 3-1 est la fenêtre la plus bruitée)")
    print()
    fmt = lambda v: f"{v:+7.1f}" if v is not None else "      —"
    print(f"  {'sym':6}{'groupe':9}{'12-1':>7}{'6-1':>7}{'3-1':>7}  {'SMA10M':9}{'compo':>6}{'accél':>7}  libellé")
    ordered = sorted(rows, key=lambda z: (z["score"] is None, z["score"] if z["score"] is not None else 99))



    hidden = 0
    if top and len(ordered) > 2 * top + 1:
        hidden = len(ordered) - 2 * top
        shown = ordered[:top] + [None] + ordered[-top:]
    else:
        shown = ordered
    for r in shown:
        if r is None:
            print(f"  {'· · ·':6}{'':9}{'':>7}{'':>7}{'':>7}  {'':9}{'':>6}{'':>7}  ({hidden} au milieu du classement — tableau entier : --group {group or 'tout'})")
            continue
        sc = f"{r['score']:5.1f}" if r["score"] is not None else "    —"
        ac = f"{r['accel']:+d}" if r["accel"] is not None else "—"
        print(f"  {r['sym']:6}{mg.label(r['group']):9}{fmt(r['m12'])}{fmt(r['m6'])}{fmt(r['m3'])}  {(r['trend'] or '—') + ('~' if r.get('trend_split') else ''):9}{sc:>6}{ac:>7}  {r['label']}")
    if ranked:


        med = {k: statistics.median([r[k] for r in ranked]) for k in ("m12", "m6", "m3")}
        print(f"\n  MÉDIANE du périmètre ({len(ranked)}) : 12-1 {fr(med['m12'])}%  6-1 {fr(med['m6'])}%  3-1 {fr(med['m3'])}%")
    if stale:
        print(f"\n  ⚠ absents du cache 1M : {', '.join(stale)}")
    print("\n  Un CLASSEMENT, pas un ordre. Aveugle aux retournements <3 mois et au M&A ;")
    print("  la décision d'entrée reste les clôtures hebdo. (Limites : en-tête du script.)")


def cmd_tree(uni, parent_group="sectors", child_group="industry"):
    """Les secteurs, chacun ouvert sur SES sous-secteurs — le parent étant"""
    import sector_map

    sec, sec_stale = momentum_rows(uni, parent_group)
    sub, sub_stale = momentum_rows(uni, child_group)
    if not sec or not sub:
        sys.exit("cache 1M vide pour un des deux périmètres — remplir d'abord (--stale --bar 1M).")
    score_rows(sec)
    score_rows(sub)
    order = sorted(sub, key=lambda z: (z["score"] is None, z["score"] if z["score"] is not None else 99))
    rank = {r["sym"]: i for i, r in enumerate(order, 1)}
    n = len(order)
    table = sector_map.load()
    tree, trans, missing = sector_map.children([r["sym"] for r in sub], table)
    by_sym = {r["sym"]: r for r in sub}

    oldest = min(r["fetched"] for r in sec + sub)
    print(f"MOMENTUM SECTEURS ET SOUS-SECTEURS — arbre — mensuel (mois complets) — cache du {oldest}")
    print(f"parent = secteur GICS dominant du sous-secteur, seuil {sector_map.THRESHOLD:.0f} % — DÉRIVÉ de sa")
    print("composition (data/etf/sectors/, fichiers émetteurs datés), jamais de son nom.")
    print(f"rang = place du sous-secteur parmi les {n} ; la part dit à quel point le parent est le bon.")
    print()
    fmt = lambda v: f"{v:+7.1f}" if v is not None else "      —"




    def line(r, prefix, width, extra=""):
        sc = f"{r['score']:5.1f}" if r["score"] is not None else "    —"
        ac = f"{r['accel']:+d}" if r["accel"] is not None else "—"
        print(f"{prefix}{r['sym']:<{width}}{fmt(r['m12'])}{fmt(r['m6'])}{fmt(r['m3'])}  "
              f"{(r['trend'] or '—') + ('~' if r.get('trend_split') else ''):9}{sc:>6}{ac:>7}  {extra}")

    print(f"  {'sym':6}{'12-1':>7}{'6-1':>7}{'3-1':>7}  {'SMA10M':9}{'compo':>6}{'accél':>7}  libellé")
    for p in sorted(sec, key=lambda z: (z["score"] is None, z["score"] if z["score"] is not None else 99)):



        kids = tree.get(p["sym"], [])
        line(p, "  ", 6, p["label"])


        for sym, pct, gics in sorted(kids, key=lambda k: rank[k[0]]):
            r = by_sym[sym]
            line(r, "  ├ ", 4, f"rang {rank[sym]:2}/{n}  {pct:.0f}% {gics}  — {r['label']}")
    if trans:
        print(f"\n  TRANSVERSE — aucun secteur ≥ {sector_map.THRESHOLD:.0f} % : ces lignes ne SONT pas")
        print("  d'un secteur. Les ranger sous leur première part afficherait comme un fait")
        print("  une pluralité — la faute que cet arbre existe pour ne pas commettre.")
        for sym, pct, gics in sorted(trans, key=lambda k: rank[k[0]]):
            r = by_sym[sym]
            w = sorted(table[sym]["weights"].items(), key=lambda kv: -kv[1])[:3]
            mix = " · ".join(f"{k} {v:.0f}%" for k, v in w)
            line(r, "  ~ ", 4, f"rang {rank[sym]:2}/{n}  {mix}")
    if missing:
        print(f"\n  ⛔ COMPOSITION NON COLLECTÉE, donc non rangées : {', '.join(missing)}")
        print("     (une ligne sans fiche ne se devine pas — la collecter : voir sector_map.py)")
    caveats = [(s, rec["caveat"]) for s, rec in table.items()
               if rec.get("caveat") and s in by_sym]
    if caveats:
        print("\n  ⚠ réserves sur la source du classement :")
        for s, c in caveats:
            print(f"     {s} — {c}")
    for label, st in (("secteurs", sec_stale), ("sous-secteurs", sub_stale)):
        if st:
            print(f"\n  ⚠ absents du cache 1M ({label}) : {', '.join(st)}")
    print("\n  Un CLASSEMENT, pas un ordre. Le parent est une lecture de composition,")
    print("  pas un véhicule : le choix du fonds se fait au cas par cas, composition en main")
    print("  (doctrine-achat — l'équipondération a cessé d'être un critère le 2026-07-22).")




def series_from_cache(uni, bar):
    import chart_identity
    out = {}
    for sym, m in uni.items():
        c = price_cache.read_cache(m["conid"])
        b = (c or {}).get("bars", {}).get(bar)
        if b:
            out[sym] = {"t": b["t"], "c": b["c"], "fetched": b["fetched"], "group": m["group"], "label": m["label"],
                        "currency": chart_identity.resolve_chart_identity(sym, universe=uni)["currency"] or "?"}
            if b.get("settled_through"):
                out[sym]["settled_through"] = b["settled_through"]
    return out


def align(base, bench, bar="1W"):
    """Ratio base/benchmark apparié par PÉRIODE (`bar_period`), daté au benchmark."""
    bt = {bar_calendar.bar_period(t, bar): c for t, c in zip(base["t"], base["c"])}
    r, ts = [], []
    for t, c in zip(bench["t"], bench["c"]):
        key = bar_calendar.bar_period(t, bar)
        if key in bt and c:
            r.append(bt[key] / c); ts.append(t)
    return r, ts


def in_usd(s, bar):
    """La série `s` en dollars, période par période ; motif (str) si impossible."""
    currency = s.get("currency") or "?"
    if currency == "USD":
        return s
    if currency == "?":
        return "devise de cotation inconnue"
    try:
        rates = fx_history.usd_rates(currency, bar)
    except fx_history.RatesUnavailable as exc:
        return str(exc)
    pairs = [(t, c * rates[key]) for t, c in zip(s["t"], s["c"])
             if c is not None and (key := bar_calendar.bar_period(t, bar)) in rates]
    if not pairs:
        return f"aucune période commune avec les taux {currency}"
    return {**s, "t": [t for t, _ in pairs], "c": [c for _, c in pairs], "currency": "USD"}


def common_currency(base, bench, bar):
    """(base, bench) dans une même devise, ou un motif de refus (str)."""
    if base.get("currency", "USD") == bench.get("currency", "USD") != "?":
        return base, bench
    converted = in_usd(base, bar), in_usd(bench, bar)
    for leg in converted:
        if isinstance(leg, str):
            return leg
    return converted


def metrics(r, windows, times=None, bar="1W"):
    """Variations du ratio par fenêtre, ancrées au CALENDRIER."""
    n = len(r)

    def chg(off):
        if n - 1 < off or not r[n - 1 - off]:
            return None
        if times is not None:
            if bar == "1M":
                return bar_calendar.calendar_return([t[:7] for t in times], r, off)
            if not bar_calendar.weeks_apart(times[-1 - off], times[-1], off):
                return None
        return (r[-1] / r[n - 1 - off] - 1) * 100
    hi = max(range(n), key=lambda i: r[i])
    w = {name: chg(off) for name, off in windows}
    off_peak = (r[-1] / r[hi] - 1) * 100
    last = windows[-1][0]; mid = windows[-2][0]
    a, b = w[mid], w[last]
    if a is None or b is None:
        tag = "historique trop court"
    else:
        tag = ("gagne, momentum" if a >= 0 and b >= 0 else "gagne mais s'essouffle" if a >= 0
               else "perd mais rebondit" if b >= 0 else "perd, momentum négatif")
    return {"w": w, "off_peak": off_peak, "tag": tag}


def _rank_key(value):
    """Clé de tri décroissant qui range une fenêtre absente (None) en dernier."""
    return float("inf") if value is None else -value


def _fr_or_dash(value):
    return "—" if value is None else fr(value)


def analyze(series, base_sym, bar):
    if base_sym not in series:
        sys.exit(f"base {base_sym} absente du cache en {bar} — tirer d'abord (--stale --bar {bar}).")


    series = {sym: {**s, **dict(zip(("t", "c"), map(list, zip(*settled))))}
              for sym, s in series.items()
              if (settled := bar_calendar.completed_series(s, bar))}
    if base_sym not in series:
        sys.exit(f"base {base_sym} sans période réglée en {bar} — tirer d'abord (--stale --bar {bar}).")
    base = series[base_sym]
    windows = WINDOWS[bar]
    rows = []
    for sym, s in series.items():
        if sym == base_sym:
            continue
        legs = common_currency(base, s, bar)
        if isinstance(legs, str):
            print(f"⚠ {base_sym}/{sym} écarté ({base.get('currency')} / {s.get('currency')}) : {legs}",
                  file=sys.stderr)
            continue
        r, ts = align(*legs, bar)
        if len(r) < 4:
            continue
        rows.append({"sym": sym, "label": s["label"], "group": s["group"], "fetched": s["fetched"],
                     "ratio": r, "times": ts, **metrics(r, windows, ts, bar)})
    return rows, windows


def text_report(rows, windows, base_sym, bar):
    out = [f"FORCE RELATIVE — base {base_sym} — barres {bar} — {len(rows)} benchmarks (depuis le cache)",
           "ratio = base/benchmark ; MONTE = base surperforme ; BAISSE = benchmark prend le leadership", ""]

    ages = {r["fetched"] for r in rows}
    oldest = min(ages) if ages else "?"
    out.append(f"fraîcheur cache : plus ancien fetch = {oldest}" + ("  ⚠ VÉRIFIER (--stale)" if oldest != today().isoformat() else "  (à jour)"))
    out.append("")
    cols = "".join(f"{w[0]:>7}" for w in windows)
    out.append(f"  {'sym':6}{'groupe':9}{cols}{'vs pic':>7}  libellé")
    out.append(f"  — classé par force relative récente ({windows[-1][0]}) —")
    for x in sorted(rows, key=lambda z: _rank_key(z["w"][windows[-1][0]])):
        vals = "".join(f"{_fr_or_dash(x['w'][w[0]]):>7}" for w in windows)
        out.append(f"  {x['sym']:6}{mg.label(x['group']):9}{vals}{fr(x['off_peak']):>7}  {x['label']}")
    cand = sorted([x for x in rows
                   if (x["w"][windows[-1][0]] or 0) < 0 and (x["w"][windows[-2][0]] or 0) < 0],
                  key=lambda z: z["w"][windows[-1][0]])
    out += ["", "  — LENTILLE ROTATION : benchmarks qui prennent le leadership sur la base (2 fenêtres récentes < 0) —"]
    out += [f"    aucun : {base_sym} surperforme sur les deux fenêtres récentes."] if not cand else \
           [f"    {x['sym']:6} {x['label']:30} {windows[-1][0]} {fr(x['w'][windows[-1][0]])}%" for x in cand]
    out += ["", "  START-DATE : lire la pente, pas un % isolé. Chiffres mécaniques ; distorsions (M&A) = à l'agent."]
    return "\n".join(out)


def render_chart(rows, windows, base_sym, bar, fragment):
    key = windows[-1][0]
    datasets, legend = [], []





    labels = sorted({t[:10] for x in rows for t in x["times"]})
    for i, x in enumerate(sorted(rows, key=lambda z: _rank_key(z["w"][key]))):
        r = x["ratio"]
        by_day = {t[:10]: round(v / r[0] * 100, 2) for t, v in zip(x["times"], r)}
        color = LINE_PALETTE[i % len(LINE_PALETTE)]
        datasets.append({"label": x["sym"], "data": [by_day.get(day) for day in labels],
                         "borderColor": color, "borderWidth": 1.5, "pointRadius": 0, "tension": 0.15})
        legend.append((x["sym"], x["label"], color, x["w"][key]))
    leg = "".join(f'<span style="display:flex;align-items:center;gap:5px;"><span style="width:10px;height:2px;'
                  f'background:{c};display:inline-block;"></span>{s} <span style="color:var(--text-muted);">{l}</span> '
                  f'<span style="color:var(--text-secondary);font-variant-numeric:tabular-nums;">{_fr_or_dash(w)}%</span></span>'
                  for s, l, c, w in legend)
    body = f'''<h2 class="sr-only" style="position:absolute;width:1px;height:1px;overflow:hidden;clip:rect(0 0 0 0);">Force relative de {base_sym} contre {len(rows)} benchmarks, barres {bar}, ratios base 100. Une ligne qui monte = {base_sym} surperforme.</h2>
<div style="padding:1rem 0;">
  <div style="font-size:13px;color:var(--text-secondary);margin-bottom:8px;">Force relative — {base_sym} / benchmark, base 100 · une ligne qui monte = {base_sym} surperforme · {bar}</div>
  <div style="position:relative;width:100%;height:340px;"><canvas id="rs" role="img" aria-label="Force relative de {base_sym}"></canvas></div>
  <div style="display:flex;flex-wrap:wrap;gap:10px 16px;margin-top:10px;font-size:12px;">{leg}</div>
  <div style="margin-top:8px;font-size:11px;color:var(--text-muted);">base {base_sym} · {bar} · chart_ratios.py (cache) · légende = variation du ratio sur {key}</div>
</div>
<script src="https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.1/chart.umd.js"></script>
<script>
(function(){{
  var isDark = matchMedia('(prefers-color-scheme: dark)').matches, grid = isDark ? '#2c2c2a' : '#e1e0d9', tick = '#898781';
  new Chart(document.getElementById('rs'), {{type:'line',
    data:{{labels:{json.dumps(labels)}, datasets:{json.dumps(datasets, ensure_ascii=False)}}},
    options:{{responsive:true,maintainAspectRatio:false,interaction:{{mode:'index',intersect:false}},
      plugins:{{legend:{{display:false}},tooltip:{{callbacks:{{title:function(t){{return t[0].label;}}}}}}}},
      scales:{{x:{{ticks:{{color:tick,maxTicksLimit:9,autoSkip:true}},grid:{{display:false}}}},y:{{ticks:{{color:tick}},grid:{{color:grid}}}}}}}}}});
}})();
</script>'''
    if fragment:
        return body
    return (f'<!doctype html><html lang="fr"><head><meta charset="utf-8">'
            f'<meta name="viewport" content="width=device-width, initial-scale=1"><title>Force relative {base_sym} {bar}</title>'
            "<style>:root{--text-primary:#0b0b0b;--text-secondary:#52514e;--text-muted:#898781;--surface:#fcfcfb;color-scheme:light dark}"
            "@media(prefers-color-scheme:dark){:root{--text-primary:#fff;--text-secondary:#c3c2b7;--text-muted:#898781;--surface:#1a1a19}}"
            "body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;background:var(--surface);color:var(--text-primary);margin:0;padding:24px;max-width:860px}</style>"
            f"</head><body>{body}</body></html>")


def main():
    ap = argparse.ArgumentParser(description="Force relative avec cache de prix incrémental.")
    ap.add_argument("--universe", action="store_true", help="lister l'univers suivi + couverture cache")
    ap.add_argument("--stale", action="store_true", help="lister ce qui manque/est périmé (plan de fetch)")
    ap.add_argument("--ingest", metavar="FILE", help="verser des barres au cache (JSON {series:{SYM:{t,c}}})")
    ap.add_argument("--bar", choices=list(BARS), default="1W", help="granularité (défaut 1W)")
    ap.add_argument("--max-age", type=int, help="âge max en jours avant 'périmé' (défaut par barre)")
    ap.add_argument("--base", help="instrument de base (défaut = base_default du manifeste)")
    ap.add_argument("--momentum", action="store_true", help="classement momentum 12-1/6-1/3-1 + SMA10M (mensuel, depuis le cache)")
    ap.add_argument("--group", help="restreindre --momentum à un/des groupe(s) du manifeste (secteur/industrie/macro/géo/marché/santé/tech/crypto/détenu)")
    ap.add_argument("--top", type=int, metavar="N", help="--momentum : n'afficher que les N premiers et N derniers du classement (le ventre est replié)")
    ap.add_argument("--tree", action="store_true",
                    help="arbre secteurs → sous-secteurs (parent DÉRIVÉ de la composition, "
                         "seuil 50 %% ; en dessous : TRANSVERSE). Rien n'est replié.")
    ap.add_argument("--chart", action="store_true", help="émettre le graphe RS au lieu du texte")
    ap.add_argument("--fragment", action="store_true", help="graphe en fragment (show_widget)")
    ap.add_argument("-o", "--out", help="écrire dans un fichier au lieu de stdout")
    a = ap.parse_args()

    uni, base_default = load_universe()
    base = a.base or base_default

    if a.universe:
        return cmd_universe(uni, base_default)
    if a.stale:
        return cmd_stale(uni, a.bar, a.max_age)
    if a.ingest:
        return cmd_ingest(a.ingest, a.bar, uni)
    if a.tree:
        return cmd_tree(uni)
    if a.momentum:
        return cmd_momentum(uni, a.group, a.top)

    series = series_from_cache(uni, a.bar)
    if not series:
        sys.exit(f"cache {a.bar} vide — lancer --stale --bar {a.bar} puis tirer et --ingest.")
    rows, windows = analyze(series, base, a.bar)
    if not rows:
        sys.exit("aucun ratio calculable.")
    result = render_chart(rows, windows, base, a.bar, a.fragment) if a.chart else text_report(rows, windows, base, a.bar)
    if a.out:
        atomic_file.write_text(pathlib.Path(a.out), result, encoding="utf-8")
        print(f"écrit : {a.out} ({len(result):,} o)")
    else:
        sys.stdout.write(result + ("\n" if not a.chart else ""))


if __name__ == "__main__":
    main()
