#!/usr/bin/env python3
"""LA RÉFÉRENCE DE CAPTEUR — une seule grammaire pour tout ce qui pointe un capteur."""
from __future__ import annotations
import data_root

import json
import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parent.parent
TRIPWIRES = data_root.tripwires_file()

KIND_LEVEL = "level"
KIND_TRIPWIRE = "tripwire"
KIND_CRITERION = "criterion"
KIND_CATALYST = "catalyst"
KINDS = (KIND_LEVEL, KIND_TRIPWIRE, KIND_CRITERION, KIND_CATALYST)
KIND_LABELS = {KIND_LEVEL: "niveau du plan", KIND_TRIPWIRE: "tripwire",
               KIND_CRITERION: "critère daté", KIND_CATALYST: "échéance"}

STATE_ARMED = "armed"
STATE_TRIGGERED = "triggered"
STATE_UNVERIFIABLE = "unverifiable"
STATES = (STATE_ARMED, STATE_TRIGGERED, STATE_UNVERIFIABLE)
STATE_LABELS = {STATE_ARMED: "armé", STATE_TRIGGERED: "déclenché",
                STATE_UNVERIFIABLE: "invérifiable"}


TOKEN = re.compile(r"^[a-z0-9][a-z0-9-]{0,63}$")
_REF = re.compile(r"^(?P<kind>[a-z]+):(?P<key>[^\s:]+)$")



def parse(ref: object) -> tuple[str, str]:
    """(kind, key) d'une référence, ou `ValueError` avec un message français."""
    if not isinstance(ref, str) or not ref.strip():
        raise ValueError(f"référence de capteur vide ou non textuelle ({ref!r})")
    match = _REF.match(ref.strip())
    if not match:
        raise ValueError(f"référence de capteur illisible : {ref!r} "
                         f"(forme attendue « genre:clé », genres {'|'.join(KINDS)})")
    kind, key = match.group("kind"), match.group("key")
    if kind not in KINDS:
        raise ValueError(f"genre de capteur inconnu : {kind!r} ({'|'.join(KINDS)})")
    if kind in (KIND_LEVEL, KIND_CATALYST):
        if not key.isdigit() or int(key) < 1:
            raise ValueError(f"{ref} : un {KIND_LABELS[kind]} se pointe par sa position, "
                             "un entier à partir de 1")
    elif not TOKEN.match(key):
        raise ValueError(f"{ref} : identifiant illisible (minuscules ASCII, chiffres, tirets)")
    return kind, key


def _criteria_ids(decision: dict | None) -> set[str]:
    """Les identifiants des critères DATÉS du bloc — un pilier n'est pas un capteur."""
    items = (decision or {}).get("criteria")
    return {str(item.get("id")) for item in items if isinstance(item, dict)
            and "pillar" not in item and item.get("id")} if isinstance(items, list) else set()


def ref_errors(ref: object, where: str = "capteur", *, decision: dict | None = None,
               facts: dict | None = None, tripwire_ids: set[str] | None = None) -> list[str]:
    """Les violations d'une référence. Liste vide = conforme."""
    try:
        kind, key = parse(ref)
    except ValueError as error:
        return [f"{where} : {error}"]
    if kind == KIND_LEVEL and decision is not None:
        levels = decision.get("levels") if isinstance(decision.get("levels"), list) else []
        if int(key) > len(levels):
            return [f"{where} : {ref} introuvable — le plan porte {len(levels)} niveau(x)"]
    if kind == KIND_CRITERION and decision is not None and key not in _criteria_ids(decision):
        return [f"{where} : {ref} introuvable — aucun critère daté de ce nom dans decision.criteria"]
    if kind == KIND_CATALYST and facts is not None:
        rows = facts.get("catalysts") if isinstance(facts.get("catalysts"), list) else []
        if int(key) > len(rows):
            return [f"{where} : {ref} introuvable — la fiche porte {len(rows)} échéance(s)"]
    if kind == KIND_TRIPWIRE and tripwire_ids is not None and key not in tripwire_ids:
        return [f"{where} : {ref} introuvable dans references/tripwires.json"]
    return []


def tripwire_ids(path: pathlib.Path | None = None) -> set[str]:
    """Les identifiants du registre des tripwires ; vide s'il est absent."""
    try:
        data = json.loads((path or TRIPWIRES).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return set()
    return {str(row.get("id")) for row in data.get("tripwires") or []
            if isinstance(row, dict) and row.get("id")}


def describe(ref: str, *, decision: dict | None = None, facts: dict | None = None) -> str:
    """Le nom lisible de la cible, en français : ce que l'investisseur reconnaît."""
    try:
        kind, key = parse(ref)
    except ValueError:
        return str(ref)
    if kind == KIND_LEVEL:
        levels = (decision or {}).get("levels") or []
        level = levels[int(key) - 1] if int(key) <= len(levels) else None
        if isinstance(level, dict):
            value = level.get("px", "règle")
            name = f" — {level['label']}" if level.get("label") else ""
            return f"niveau {key} : {level.get('bar')} {level.get('op')} {value}{name}"
        return f"niveau {key}"
    if kind == KIND_CATALYST:
        rows = (facts or {}).get("catalysts") or []
        row = rows[int(key) - 1] if int(key) <= len(rows) else None
        if isinstance(row, dict):
            return f"échéance {key} : {row.get('date') or 'sans date'} — {str(row.get('what') or '')[:80]}"
        return f"échéance {key}"
    return f"{KIND_LABELS[kind]} {key}"
