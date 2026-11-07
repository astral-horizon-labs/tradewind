#!/usr/bin/env python3
"""LE STATUT DES DATES DE CATALYSEUR — certitude, date annoncée, glissement."""
from __future__ import annotations
import data_root

import argparse
import datetime
import json
import pathlib
import sys

import catalyst_kinds

HERE = pathlib.Path(__file__).resolve().parent
SHEETS = data_root.book_refs() / "instruments"


CERTAINTY_LABELS = {"confirmed": "Date confirmée", "estimated": "Estimation"}




BASIS_LABELS = {
    "declared": "déclarée sur la fiche",
    "text": "déduite du texte",
    "measured": "mesurée sur le rythme des dépôts",
    "fixed": "fixée à la source",
}





CONFIRMED_MARKERS = (
    "échéance légale", "date butoir", "pdufa", "fixée au", "fixé au",
    "date confirmée", "date confirmé", "assemblée le", "commercial day",
)

WINDOW_MARKERS = (
    "fenêtre", "trimestre", "semestre", "fin 20", "q1-", "q2-", "q3-", "q4-",
    "t1-", "t2-", "t3-", "t4-", "h1-", "h2-", "1h-", "2h-", "objectif",
    "guidé", "guidée", "attendu", "attendue", "estimé", "estimée", "vers le",
    "sous réserve",
)


def _iso_day(value: object) -> datetime.date | None:
    if not isinstance(value, str):
        return None
    try:
        return datetime.date.fromisoformat(value)
    except ValueError:
        return None


def row_problems(row: object) -> list[str]:
    """Les défauts de `certainty` et `guided` sur UN catalyseur (liste vide si sain)."""
    if not isinstance(row, dict):
        return []
    problems: list[str] = []
    if "certainty" in row:
        certainty = row["certainty"]
        if not isinstance(certainty, str) or certainty not in CERTAINTY_LABELS:
            problems.append(f"certainty {certainty!r} inconnue (attendu : {', '.join(CERTAINTY_LABELS)})")
    if "guided" in row and _iso_day(row["guided"]) is None:
        problems.append(f"guided {row['guided']!r} invalide (attendu une date AAAA-MM-JJ)")
    return problems


def certainty_from_text(text: str) -> str:
    """N'affirme une date que lorsque la prose la qualifie explicitement."""
    normalized = (text or "").casefold()
    return "confirmed" if any(marker in normalized for marker in CONFIRMED_MARKERS) else "estimated"


def is_window(text: str, certainty: str) -> bool:
    """Une date ESTIMÉE dont la prose dit qu'elle borne une fenêtre."""
    normalized = (text or "").casefold()
    return certainty == "estimated" and any(marker in normalized for marker in WINDOW_MARKERS)


def certainty_of(row: object, text: str) -> tuple[str, str]:
    """(certitude, base) — la clé déclarée prime ; sans elle, la prose, et la base le dit."""
    declared = row.get("certainty") if isinstance(row, dict) else None
    if declared in CERTAINTY_LABELS:
        return declared, "declared"
    return certainty_from_text(text), "text"


def guided_of(row: object) -> str | None:
    """La date annoncée en premier, si elle est une date valide."""
    guided = row.get("guided") if isinstance(row, dict) else None
    return guided if _iso_day(guided) else None


def slip_days(row: object, date: str) -> int | None:
    """Jours entre la date annoncée (`guided`) et la date courante ; None sans les deux."""
    guided, current = _iso_day(guided_of(row)), _iso_day(date)
    if guided is None or current is None:
        return None
    return (current - guided).days


def _french_day(iso: str) -> str:
    year, month, day = iso.split("-")
    return f"{day}/{month}/{year}"


def slip_label(guided: str | None, slip: int | None) -> str | None:
    """« annoncé pour le 30/09/2026, glissé de 41 jours » ; None sans glissement."""
    if not guided or not slip:
        return None
    days = abs(slip)
    unit = "jour" if days == 1 else "jours"
    moved = "glissé" if slip > 0 else "avancé"
    return f"annoncé pour le {_french_day(guided)}, {moved} de {days} {unit}"


def certainty_label(certainty: str, basis: str) -> str:
    """« Date confirmée · déclarée sur la fiche » — la base est toujours dite."""
    return f"{CERTAINTY_LABELS.get(certainty, certainty)} · {BASIS_LABELS.get(basis, basis)}"




def _catalyst_rows(sheet: object) -> list:
    facts = sheet.get("facts") if isinstance(sheet, dict) else None
    rows = facts.get("catalysts") if isinstance(facts, dict) else None
    return rows if isinstance(rows, list) else []


def sheet_problems(sheet: object) -> list[str]:
    """Les défauts de `certainty` et `guided` sur toute la liste d'une fiche."""
    return [f"catalyseur {index} : {problem}"
            for index, row in enumerate(_catalyst_rows(sheet), start=1) for problem in row_problems(row)]


def check_sheet(sheet: object) -> None:
    """Lève ValueError si une `certainty` ou un `guided` est mal formé — appelé par `jsonio.write`."""
    problems = sheet_problems(sheet)
    if problems:
        raise ValueError("catalyseur refusé : " + " ; ".join(problems))


def sheet_status(sheet: object) -> list[dict]:
    """Chaque catalyseur DATÉ d'une fiche : certitude et sa base, date annoncée, glissement, source."""
    out = []
    for index, row in enumerate(_catalyst_rows(sheet)):
        if not isinstance(row, dict) or _iso_day(row.get("date")) is None:
            continue
        what = str(row.get("what") or "").strip()
        certainty, basis = certainty_of(row, what)
        guided = guided_of(row)
        slip = slip_days(row, row["date"])
        out.append({
            "index": index, "date": row["date"], "what": what, "certainty": certainty, "basis": basis,
            "label": certainty_label(certainty, basis), "guided": guided, "slip_days": slip,
            "slip_label": slip_label(guided, slip), "source": catalyst_kinds.valid_source(row),
        })
    return out


def load_sheets(path: pathlib.Path | None = None) -> dict[str, dict]:
    out: dict[str, dict] = {}
    for sheet_path in sorted(pathlib.Path(path or SHEETS).glob("*.json")):
        sheet = json.loads(sheet_path.read_text(encoding="utf-8"))
        if isinstance(sheet, dict):
            out[str(sheet.get("symbol") or sheet_path.stem).upper()] = sheet
    return out


def coverage(sheets: dict[str, dict]) -> dict:
    """Combien de dates portent une certitude DÉCLARÉE, une date annoncée, un glissement."""
    rows = [row for sheet in sheets.values() for row in sheet_status(sheet)]
    return {
        "dated": len(rows),
        "declared": sum(row["basis"] == "declared" for row in rows),
        "from_text": sum(row["basis"] == "text" for row in rows),
        "guided": sum(row["guided"] is not None for row in rows),
        "slipped": sum(bool(row["slip_days"]) for row in rows),
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Certitude, date annoncée et glissement des catalyseurs datés des fiches.")
    ap.add_argument("--symbol", metavar="SYM", help="une seule fiche")
    ap.add_argument("--slipped", action="store_true", help="seulement les échéances qui ont glissé")
    ap.add_argument("--check", action="store_true",
                    help="relit toutes les fiches ; rc=1 si une certainty ou un guided est mal formé")
    ap.add_argument("--json", action="store_true", help="sortie JSON")
    args = ap.parse_args(argv)
    sheets = load_sheets()
    if args.symbol:
        wanted = args.symbol.strip().upper()
        sheets = {symbol: sheet for symbol, sheet in sheets.items() if symbol == wanted}
        if not sheets:
            print(f"Aucune fiche {wanted}.")
            return 1
    if args.check:
        bad = 0
        for symbol, sheet in sheets.items():
            problems = sheet_problems(sheet)
            for problem in problems:
                print(f"  {symbol} : {problem}")
            bad += bool(problems)
        print(f"{bad} fiche(s) à corriger." if bad else "Aucune certainty ni guided mal formé.")
        return 1 if bad else 0
    rows = [{"symbol": symbol, **row} for symbol, sheet in sheets.items() for row in sheet_status(sheet)]
    if args.slipped:
        rows = [row for row in rows if row["slip_days"]]
    if args.json:
        print(json.dumps({"rows": rows, "coverage": coverage(sheets)}, ensure_ascii=False, indent=1))
        return 0
    for row in rows:
        slip = f" — {row['slip_label']}" if row["slip_label"] else ""
        print(f"  {row['date']}  {row['symbol']:8} {row['label']}{slip}")
        print(f"      {row['what'][:110]}")
    counts = coverage(sheets)
    print(f"\n{counts['dated']} catalyseur(s) daté(s) : certitude déclarée sur {counts['declared']}, "
          f"déduite du texte sur {counts['from_text']} ; date annoncée portée sur {counts['guided']}, "
          f"glissement sur {counts['slipped']}.")
    if counts["from_text"]:
        print("  Une certitude déduite du texte est une lecture de mots, pas un fait : "
              "la déclarer (`certainty`) quand la source est lue.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
