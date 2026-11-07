"""Les groupes du manifeste : un jeton anglais, un libellé français."""
from __future__ import annotations

import unicodedata


LABELS = {
    "bonds": "obligations",
    "consumer": "consommation",
    "crypto": "crypto",
    "crypto-spot": "crypto-spot",
    "defense": "défense",
    "energy": "énergie",
    "financials": "finance",
    "former-held": "ex-détenu",
    "health": "santé",
    "held": "détenu",
    "industry": "industrie",
    "macro": "macro",
    "market": "marché",
    "metals": "métaux",
    "quantum": "quantique",
    "rates": "taux",
    "regions": "géo",
    "robotics": "robotique",
    "sectors": "secteur",
    "tech": "tech",
    "themes": "thème",
    "transport": "transport",
    "travel": "voyage",
    "volatility": "volatilité",
}


HELD = "held"
FORMER_HELD = "former-held"

CRYPTO_SPOT = "crypto-spot"









CRYPTO_VENUES = {"coinbase-spot": "coinbase", "hyperliquid-spot": "hyperliquid",
                 "eodhd-crypto": "eodhd"}
EODHD_VENUE = "eodhd"


def crypto_venue(entry: dict | None) -> str | None:
    """La source d'une série crypto 24/7 d'après son manifeste ; None sinon."""
    entry = entry or {}
    venue = CRYPTO_VENUES.get(entry.get("source"))
    if venue and entry.get("eodhd_code"):
        return EODHD_VENUE
    return venue


def crypto_control_venue(entry: dict | None) -> str | None:
    """La bourse qui contrôle une série tirée d'EODHD : celle de `source`, ou None."""
    entry = entry or {}
    if crypto_venue(entry) != EODHD_VENUE:
        return None
    venue = CRYPTO_VENUES.get(entry.get("source"))
    return None if venue == EODHD_VENUE else venue


def _fold(value: str) -> str:
    """Minuscules sans diacritiques : « Santé », « sante » et « SANTÉ » se valent."""
    decomposed = unicodedata.normalize("NFD", value.strip())
    return "".join(c for c in decomposed if unicodedata.category(c) != "Mn").lower()


_BY_INPUT = {**{_fold(token): token for token in LABELS},
             **{_fold(label): token for token, label in LABELS.items()}}


def canonical(value: str) -> str:
    """Le jeton d'un groupe tapé en jeton ou en libellé ; `ValueError` sinon."""
    token = _BY_INPUT.get(_fold(str(value)))
    if token is None:
        raise ValueError(
            f"groupe inconnu {value!r} — groupes du manifeste : "
            + ", ".join(f"{label} ({token})" for token, label in sorted(LABELS.items())))
    return token


def parse_list(value: str | None) -> list[str]:
    """`"santé,géo"` → `["health", "regions"]`, ordre gardé, doublons retirés."""
    tokens = [canonical(part) for part in str(value or "").split(",") if part.strip()]
    return list(dict.fromkeys(tokens))


def label(token: str | None) -> str:
    """Le libellé français d'un jeton ; un jeton inconnu s'affiche tel quel."""
    return LABELS.get(token or "", token or "")


def of(meta: dict) -> set[str]:
    """Les groupes d'une entrée du manifeste : `groups` s'il existe, sinon `group`."""
    return {g for g in (meta.get("groups") or [meta.get("group")]) if g}
