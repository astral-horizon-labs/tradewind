#!/usr/bin/env python3
"""Paliers de trailing MOBILES — la loi de calcul, une seule fois."""
from __future__ import annotations
import data_root
import argparse, pathlib, sys

import bar_calendar
import price_cache

HERE = pathlib.Path(__file__).resolve().parent
RULES = ("higher-low",)
DEFAULT_CONFIRM = 2


def swing_lows(bars, confirm):
    """[(index, date, bas)] des creux CONFIRMÉS — `confirm` barres plus hautes"""
    lo, ts = bars["l"], bars["t"]
    out = []
    for i in range(confirm, len(lo) - confirm):
        w = lo[i - confirm:i + confirm + 1]
        if lo[i] == min(w) and w.count(lo[i]) == 1:
            out.append((i, ts[i][:10], lo[i]))
    return out


def ladder(bars, seed, confirm=DEFAULT_CONFIRM, since=None):
    """[(date, palier)] — l'escalier du cliquet, une marche par RELÈVEMENT."""
    start = since or bars["t"][0][:10]
    steps = [(start, float(seed))]
    cur = float(seed)
    for _, date, low in swing_lows(bars, confirm):
        if date >= start and low > cur:
            cur = low
            steps.append((date, cur))
    return steps


def palier(bars, seed, confirm=DEFAULT_CONFIRM, since=None):
    """(niveau courant, date du dernier relèvement) — ce que tripwires compare."""
    steps = ladder(bars, seed, confirm, since)
    return steps[-1][1], steps[-1][0]


def cadence(bars, seed, confirm=DEFAULT_CONFIRM, since=None):
    """(bascules, périodes jugées, détail) — combien de fois une clôture serait"""
    steps = ladder(bars, seed, confirm, since)
    start = steps[0][0]
    hits, cur, si, n = [], steps[0][1], 0, 0
    for t, c in zip(bars["t"], bars["c"]):
        d = t[:10]
        if d < start:
            continue
        n += 1
        while si + 1 < len(steps) and steps[si + 1][0] <= d:
            si += 1
            cur = steps[si][1]
        if c < cur:
            hits.append((d, c, cur))
    return len(hits), n, hits


def validate(tr):
    """Raison du rejet, ou None. Nomme toujours le champ — même grammaire"""
    if not isinstance(tr, dict):
        return "`trail` doit être un objet {rule, seed, confirm}"
    if tr.get("rule") not in RULES:
        return f"`trail.rule` « {tr.get('rule')} » inconnu (attendu : {'|'.join(RULES)})"
    if not isinstance(tr.get("seed"), (int, float)):
        return f"`trail.seed` non numérique ({tr.get('seed')!r}) — le point de départ est ratifié par {data_root.owner_label()}, jamais deviné"
    c = tr.get("confirm", DEFAULT_CONFIRM)
    if not isinstance(c, int) or c < 1:
        return f"`trail.confirm` doit être un entier ≥ 1 ({c!r})"
    return None


def keep_periods(b, kept):
    """Copie des barres réduite aux horodatages de `kept`, champs alignés."""
    index = [i for i, ts in enumerate(b.get("t", [])) if ts in kept]
    out = dict(b)
    for key in ("t", "o", "h", "l", "c", "v"):
        values = b.get(key)
        if isinstance(values, list):
            out[key] = [values[i] for i in index]
    return out


def _load(sym):
    import json
    uni = json.loads((data_root.universe_file()).read_text())["instruments"]
    if sym not in uni:
        sys.exit(f"{sym} absent de ratio-universe.json — ajouter le conid au manifeste")
    b = (price_cache.read_cache(uni[sym]["conid"]) or {}).get("bars", {}).get("1W")
    if not b:
        sys.exit(f"cache 1W absent pour {sym}")
    return b


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("symbol")
    ap.add_argument("--seed", type=float, required=True)
    ap.add_argument("--confirm", type=int, default=DEFAULT_CONFIRM)
    ap.add_argument("--since", help="date d'activation AAAA-MM-JJ (défaut : tout le cache)")
    ap.add_argument("--cadence", action="store_true", help="compter les bascules historiques")
    a = ap.parse_args()





    raw = _load(a.symbol)
    b = keep_periods(raw, {ts for ts, _close in bar_calendar.completed_series(raw, "1W")})
    if not b.get("c"):
        sys.exit(f"aucune semaine réglée au cache 1W pour {a.symbol}")
    px, when = palier(b, a.seed, a.confirm, a.since)
    close = b["c"][-1]
    marge = (close / px - 1) * 100
    steps = ladder(b, a.seed, a.confirm, a.since)
    print(f"{a.symbol} — seed {a.seed}  confirm {a.confirm} semaine(s)")
    print(f"  palier courant : {px:.4g}   (relevé le {when})")
    print(f"  clôture 1W     : {close:.4g}   → marge {marge:+.1f} %")
    print(f"  escalier       : {len(steps)} marche(s) — " +
          " → ".join(f"{p:.4g}" for _, p in steps[-6:]))
    if a.cadence:
        n, tot, hits = cadence(b, a.seed, a.confirm, a.since)
        print(f"\n  CADENCE : {n} bascule(s) sur {tot} semaines jugées"
              + (f" depuis {a.since}" if a.since else " (tout le cache)"))
        for d, c, lvl in hits[-8:]:
            print(f"    {d}  clôture {c:.4g} < palier {lvl:.4g}")


if __name__ == "__main__":
    main()
