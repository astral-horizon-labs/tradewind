"""Lecture canonique des fiches instrument pour les outils du domaine."""
from __future__ import annotations
import data_root
from derived_cache import DerivedCache, files_signature

import json
from datetime import date
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
SHEETS = data_root.book_refs() / "instruments"
WATCHLIST_TV = data_root.book_refs() / "watchlist-tv.json"





SCOPE_HOLDING = "holding"
SCOPE_CANDIDATE = "candidate"
SCOPE_REFERENCE = "reference"


def is_fund(record: dict | None) -> bool:
    """Un fonds (ETF ou ETP) à traverser, d'après le stade OU la catégorie."""
    if not isinstance(record, dict):
        return False
    stage = str(record.get("stage") or "").strip().lower()
    if stage:
        return stage == "etf"
    return str(record.get("cat") or "").startswith("etf")


def new_sheet(symbol: str, *, name: str, exchange: str | None, conid, provenance: dict,
              today: str | None = None) -> dict:
    """Le squelette d'une fiche neuve : identité seule, rien d'instruit."""
    return {
        "version": 1,
        "symbol": symbol,
        "identity": {
            "name": name,
            "exchange": exchange,
            "conid": conid,
            "category": None,
            "stage": None,
            "geo": None,
        },
        "state": {
            "verified_on": None,
            "updated_on": today or date.today().isoformat(),
        },
        "facts": {},
        "tripwires": [],
        "research": [],
        "provenance": provenance,
    }


def records(path: Path | None = None) -> dict[str, dict]:
    """Rend les fiches sous l'enveloppe plate attendue par les calculs existants."""
    path = path or SHEETS
    return _RECORDS.get(
        lambda: (str(path.resolve()), files_signature(path.glob("*.json"))),
        lambda: _read_records(path))


_RECORDS = DerivedCache(max_entries=4)


def _read_records(path: Path) -> dict[str, dict]:
    """Le calcul de `records`, sans mémoire."""
    result: dict[str, dict] = {}
    for sheet_path in sorted(path.glob("*.json")):
        sheet = json.loads(sheet_path.read_text(encoding="utf-8"))
        symbol = str(sheet.get("symbol") or sheet_path.stem).upper()
        identity = sheet.get("identity") if isinstance(sheet.get("identity"), dict) else {}
        state = sheet.get("state") if isinstance(sheet.get("state"), dict) else {}
        facts = sheet.get("facts") if isinstance(sheet.get("facts"), dict) else {}
        entry = {
            "name": identity.get("name") or symbol,
            "conid": identity.get("conid"),
            "cik": identity.get("cik"),
            "cat": identity.get("category"),
            "stage": identity.get("stage"),
            "geo": identity.get("geo"),
            "domicile": identity.get("domicile"),
            "verified_on": state.get("verified_on"),
            "detail": facts.get("detail"),
            "cash": facts.get("cash"),
            "stage_risk_reason": facts.get("risk"),
            "constat": facts.get("observation"),
            "catalysts": facts.get("catalysts") or [],
            "sec_financials": facts.get("sec_financials"),
            "plan": sheet.get("decision"),
        }
        result[symbol] = {key: value for key, value in entry.items() if value is not None}
    return result


def classification_records(fixture=None) -> dict:
    """Les fiches qui portent le classement (`cat`, `geo`) : les fiches"""
    if fixture is not None:
        return json.loads(Path(fixture).read_text(encoding="utf-8"))
    return records()


def holding_records(snapshot: dict | None = None) -> dict[str, dict]:
    """Restreint les faits aux positions du snapshot, identité de contrat comprise."""
    import book

    if snapshot is None:


        path = book.latest_snapshot()
        if path is None:
            raise FileNotFoundError("Aucun snapshot pour déterminer les positions détenues.")
        snapshot = book.load_snapshot(path)
    source = records()
    result = {}
    for symbol, position in snapshot["lines"].items():
        contract = str(position.get("conid") or "")
        entry = source.get(symbol)
        if entry is not None:
            if contract and entry.get("conid") and str(entry["conid"]) != contract:
                raise ValueError(f"{symbol} : le contrat de la fiche diffère du snapshot.")
            result[symbol] = entry
            continue
        aliases = [entry for entry in source.values()
                   if contract and str(entry.get("conid") or "") == contract]
        if len(aliases) > 1:
            raise ValueError(f"{symbol} : plusieurs fiches portent le contrat {contract}.")
        result[symbol] = aliases[0] if aliases else {}
    return result


def review_date(value: object) -> str | None:
    """Une date absente, invalide ou future ne prouve aucune relecture."""
    if not isinstance(value, str):
        return None
    try:
        reviewed = date.fromisoformat(value)
    except ValueError:
        return None
    return reviewed.isoformat() if reviewed <= date.today() else None


def watchlist_symbols(path: Path | None = None) -> set[str]:
    """L'appartenance à sa liste de candidats Wallet — la SEULE source de ce fait."""
    source = path or WATCHLIST_TV
    if not source.exists():
        return set()
    document = json.loads(source.read_text(encoding="utf-8"))
    return {str(symbol).upper() for symbol in (document.get("symbols") or [])}


def scope_of(symbol: str, *, held: set[str], watchlist: set[str] | None = None) -> str:
    """Le périmètre d'une fiche, DÉDUIT de deux faits et jamais stocké."""
    normalized = symbol.upper()
    if normalized in held:
        return SCOPE_HOLDING
    known = watchlist_symbols() if watchlist is None else watchlist
    return SCOPE_CANDIDATE if normalized in known else SCOPE_REFERENCE
