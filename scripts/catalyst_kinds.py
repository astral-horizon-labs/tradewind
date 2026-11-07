#!/usr/bin/env python3
"""LE REGISTRE DES NATURES DE CATALYSEUR — `kind`, `source` et `shares` sur `facts.catalysts`."""
from __future__ import annotations
import data_root

import argparse
import json
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
SHEETS = data_root.book_refs() / "instruments"


FAMILY_OVERHANG = "overhang"
FAMILY_LABELS = {FAMILY_OVERHANG: "Surplomb"}




KINDS: dict[str, tuple[str, str | None]] = {
    "filing": ("Dépôt réglementaire", None),
    "earnings": ("Résultats", None),
    "regulatory": ("Décision réglementaire", None),
    "event": ("Événement", None),
    "lockup_expiry": ("Levée de lock-up", FAMILY_OVERHANG),
    "resale_effective": ("Revente effective", FAMILY_OVERHANG),
    "warrant_expiry": ("Expiration de bons", FAMILY_OVERHANG),
}
KIND_LABELS = {token: label for token, (label, _family) in KINDS.items()}
OVERHANG_KINDS = frozenset(token for token, (_label, family) in KINDS.items() if family == FAMILY_OVERHANG)


def family(kind: object) -> str | None:
    """La famille d'un jeton (`overhang`), ou None pour une nature ordinaire ou inconnue."""
    entry = KINDS.get(kind) if isinstance(kind, str) else None
    return entry[1] if entry else None


def is_overhang(row: object) -> bool:
    """La ligne de catalyseur est-elle un surplomb déclaré ?"""
    return isinstance(row, dict) and row.get("kind") in OVERHANG_KINDS


def _source_is_valid(source: object) -> bool:
    return isinstance(source, str) and source.startswith("https://") and not any(ch.isspace() for ch in source)


def valid_source(row: object) -> str | None:
    """La `source` d'un catalyseur si elle est une URL https:// sans espace ; None sinon."""
    source = row.get("source") if isinstance(row, dict) else None
    return source if _source_is_valid(source) else None


def row_problems(row: object) -> list[str]:
    """Les défauts de `kind`, `source` et `shares` sur UN catalyseur (liste vide si sain)."""
    if not isinstance(row, dict):
        return [f"ligne {type(row).__name__} au lieu d'un objet {{date, what, …}}"]
    problems: list[str] = []
    if "kind" in row:
        kind = row["kind"]
        if not isinstance(kind, str) or kind not in KINDS:
            problems.append(f"kind {kind!r} inconnu (attendu : {', '.join(KINDS)})")
    if "source" in row:
        source = row["source"]
        if not _source_is_valid(source):
            problems.append(f"source {source!r} invalide (attendu une URL https:// sans espace)")
    if "shares" in row:
        shares = row["shares"]

        if isinstance(shares, bool) or not isinstance(shares, int) or shares <= 0:
            problems.append(f"shares {shares!r} invalide (attendu un entier strictement positif)")
    return problems


def sheet_problems(sheet: object) -> list[str]:
    """Les défauts de toute la liste `facts.catalysts` d'une fiche."""
    facts = sheet.get("facts") if isinstance(sheet, dict) else None
    rows = facts.get("catalysts") if isinstance(facts, dict) else None
    if not isinstance(rows, list):
        return []
    return [f"catalyseur {index} : {problem}"
            for index, row in enumerate(rows, start=1) for problem in row_problems(row)]


def check_sheet(sheet: object) -> None:
    """Lève ValueError si une clé est mal formée — appelé par `jsonio.write`."""
    problems = sheet_problems(sheet)
    if problems:
        raise ValueError("catalyseur refusé : " + " ; ".join(problems))


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Natures de catalyseur (kind, source, shares) des fiches.")
    ap.add_argument("--check", action="store_true", help="relit toutes les fiches ; rc=1 si une clé est mal formée")
    args = ap.parse_args(argv)
    if not args.check:
        for token, (label, kind_family) in KINDS.items():
            suffix = f" — {FAMILY_LABELS[kind_family]}" if kind_family else ""
            print(f"  {token:18} {label}{suffix}")
        return 0
    bad = 0
    for path in sorted(SHEETS.glob("*.json")):
        problems = sheet_problems(json.loads(path.read_text(encoding="utf-8")))
        for problem in problems:
            print(f"  {path.stem} : {problem}")
        bad += bool(problems)
    print(f"{bad} fiche(s) à corriger." if bad else "Aucune clé de catalyseur mal formée.")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
