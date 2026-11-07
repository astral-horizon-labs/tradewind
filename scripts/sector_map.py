#!/usr/bin/env python3
"""Parent sectoriel d'un sous-secteur — DÉRIVÉ de sa composition, jamais de son nom."""
from __future__ import annotations
import json, pathlib

HERE = pathlib.Path(__file__).resolve().parent
SECTORS_DIR = HERE.parent / "data" / "etf" / "sectors"
THRESHOLD = 50.0



GICS_ETF = {
    "Information Technology": "XLK",
    "Health Care":            "XLV",
    "Financials":             "XLF",
    "Energy":                 "XLE",
    "Industrials":            "XLI",
    "Consumer Discretionary": "XLY",
    "Consumer Staples":       "XLP",
    "Utilities":              "XLU",
    "Materials":              "XLB",
    "Real Estate":            "XLRE",
    "Communication Services": "XLC",
}





RBICS_GICS = {
    "Communications": "Communication Services",
    "Consumer Durables": "Consumer Discretionary",
    "Consumer Non-Durables": "Consumer Staples",
    "Consumer Services": "Consumer Discretionary",
    "Distribution Services": "Industrials",
    "Electronic Technology": "Information Technology",
    "Energy Minerals": "Energy",
    "Finance": "Financials",
    "Health Services": "Health Care",
    "Health Technology": "Health Care",
    "Industrial Services": "Industrials",
    "Non-Energy Minerals": "Materials",
    "Process Industries": "Materials",
    "Producer Manufacturing": "Industrials",
    "Retail Trade": "Consumer Discretionary",
    "Technology Services": "Information Technology",
    "Transportation": "Industrials",
    "Utilities": "Utilities",
}

ALIAS = {
    "Communication":     "Communication Services",
    "Info Technology":   "Information Technology",
    "Information Tech":  "Information Technology",
    "Healthcare":        "Health Care",
    "Consumer Staple":   "Consumer Staples",
}


NON_GICS = {"Other", "Unassigned"}






SANS_GICS = {
    "BATT": "Amplify ne publie qu'une « Market Allocation » MAISON (Copper 21,8 %, "
            "Electric Vehicles 18,1 %, Battery Technology 13,5 %, Nickel 12,3 %, "
            "Battery Components 11,1 %, Lithium 8,4 %, Energy Storage 7,2 %, "
            "Cobalt 3,9 %, Manganese 1,6 %, Other 2,2 % — au 30/06/2026). Aucun "
            "bloc GICS sur la page ni dans la fiche produit PDF (cherché le "
            "2026-07-22). Le fonds n'est PAS mono-secteur : il tient Tesla, BYD, "
            "Rivian, NIO (Consumer Discretionary), Panasonic/TDK/Samsung SDI "
            "(Information Technology) et BHP/Freeport (Materials).",
    "SETM": "Sprott ne publie que des « Material Weightings » MAISON (Copper 26,6 %, "
            "Uranium 25,2 %, Lithium 19,1 %, Silver 14,6 %, Rare Earths 11,4 %, "
            "Nickel 2,1 %, Manganese 0,5 %, Recyclers 0,4 %, Graphite 0,1 % — au "
            "30/06/2026), explicitement « classified by Sprott Asset Management ». "
            "Aucun bloc GICS sur la page ni dans le factsheet (cherché le "
            "2026-07-22). Les convertir SOI-MÊME serait inventer : GICS range les "
            "mineurs d'uranium en ENERGY et les mineurs de cuivre en MATERIALS — "
            "« c'est du minier donc Materials » se tromperait sur un quart du fonds.",
    "PALL": "Trust de PALLADIUM physique — un lingot n'a pas de secteur. "
            "Structurellement hors arbre, comme PDBA l'est du look-through.",
    "PLTM": "Trust de PLATINE physique — même raison que PALL.",
}


def canon(label):
    """Libellé émetteur -> secteur GICS canonique. Lève sur l'inconnu."""
    lab = ALIAS.get(label, label)
    if lab in GICS_ETF or lab in NON_GICS:
        return lab
    raise KeyError(f"libellé sectoriel inconnu : « {label} » — ajouter à GICS_ETF "
                   f"ou ALIAS après avoir vérifié à quoi il correspond chez l'émetteur")


def load(directory=None):
    """{sym: fiche} — les compositions collectées, telles qu'écrites."""
    d = pathlib.Path(directory) if directory else SECTORS_DIR
    out = {}
    for f in sorted(d.glob("*.json")):
        rec = json.loads(f.read_text())
        rec["weights"] = {canon(k): v for k, v in rec["weights"].items()}
        out[rec["symbol"]] = rec
    return out


def parent(sym, table=None, threshold=THRESHOLD):
    """(etf_parent | None, part, secteur_gics | None, fiche | None)."""
    t = table if table is not None else load()
    rec = t.get(sym)
    if rec is None:
        return None, None, None, None
    ranked = [(k, v) for k, v in rec["weights"].items() if k not in NON_GICS]
    if not ranked:
        return None, None, None, rec
    gics, pct = max(ranked, key=lambda kv: kv[1])
    return (GICS_ETF[gics] if pct >= threshold else None), pct, gics, rec


def children(syms, table=None, threshold=THRESHOLD):
    """({etf_parent: [(sym, part, gics)]}, transverses, sans_fiche) — l'arbre,"""
    t = table if table is not None else load()
    tree, trans, missing = {}, [], []
    for s in syms:
        etf, pct, gics, rec = parent(s, t, threshold)
        if rec is None:
            missing.append(s)
        elif etf is None:
            trans.append((s, pct, gics))
        else:
            tree.setdefault(etf, []).append((s, pct, gics))
    for v in tree.values():
        v.sort(key=lambda x: -x[1])
    trans.sort(key=lambda x: -(x[1] or 0))
    return tree, trans, missing


def basket_parent(sector_counts, classified, threshold=THRESHOLD):
    """Parent d'un panier depuis les secteurs RBICS de ses MEMBRES."""
    if not classified:
        return None, None, None
    gics_counts = {}
    for rbics, count in sector_counts.items():
        gics = RBICS_GICS.get(rbics)
        if gics:
            gics_counts[gics] = gics_counts.get(gics, 0) + count
    if not gics_counts:
        return None, 0.0, None
    gics, count = max(gics_counts.items(), key=lambda item: item[1])
    pct = count / classified * 100
    return (GICS_ETF[gics] if pct >= threshold else None), pct, gics


def main():
    t = load()
    print(f"PARENT SECTORIEL — dérivé de {len(t)} compositions collectées "
          f"(data/etf/sectors/), seuil {THRESHOLD:.0f} %\n")
    print(f"  {'sym':6}{'parent':7}{'secteur GICS dominant':26}{'part':>7}  {'source (au)':12}")
    print("  " + "-" * 72)
    rows = []
    for s in t:
        etf, pct, gics, rec = parent(s, t)
        rows.append((pct, s, etf, gics, rec))


    for pct, s, etf, gics, rec in sorted(rows, key=lambda r: -(r[0] or 0)):
        flag = etf or "TRANSV"
        note = " ⚠" if rec.get("caveat") else ""
        part = f"{pct:6.1f}%" if pct is not None else "     —"
        print(f"  {s:6}{flag:7}{gics or '—':26}{part}  {rec['as_of']:12}{note}")
    trans = [r for r in rows if r[2] is None]
    print(f"\n  TRANSVERSE (aucun secteur ≥ {THRESHOLD:.0f} %) : "
          f"{', '.join(r[1] for r in trans) or 'aucun'}")
    print(f"\n  SANS GICS PUBLIÉ ({len(SANS_GICS)}) — absence CONSTATÉE, pas collecte en retard :")
    for s, why in sorted(SANS_GICS.items()):
        print(f"    {s} — {why.split('.')[0]}.")

    caveats = [r for r in rows if r[4].get("caveat")]
    if caveats:
        print("\n  ⚠ fiches portant une réserve :")
        for _, s, _, _, rec in caveats:
            print(f"    {s} — {rec['caveat']}")


if __name__ == "__main__":
    main()
