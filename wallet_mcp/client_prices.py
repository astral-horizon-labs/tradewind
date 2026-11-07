"""Les prix d'un client, servis par NOTRE serveur de prix — pas par une clé à lui.

POURQUOI (2026-11-07, décision du propriétaire). Le Flex donne le compte, pas
l'historique des cours. Le client ne s'abonne à rien : le MCP lit les séries que
notre collecte publie déjà sur le serveur privé (Worker Cloudflare devant R2,
`server/prices-worker`, client `scripts/prices_server.py`). Elles y sont rangées
par conid IBKR, l'identifiant que porte chaque ligne du rapport Flex : le raccord
se fait sans table de correspondance.

Configuration, dans le même `client.json` que le Flex :
    "prices_url": "https://…",            le Worker (`DEFAULT_URL` par défaut)
    "prices_key_file": "~/…/prices.key"   ou "prices_key": "…" — jamais affichée
La clé s'obtient seule à l'installation (`register`, 2026-11-07) : le Worker en
délivre une par `POST /v1/keys`, plafonnée en requêtes.

Une série gardée moins de `MAX_AGE_S` se relit sur le disque du client ; au-delà on
la retire. Un serveur injoignable rend la copie gardée, avec l'erreur et sa date.
Seules les clôtures RÉGLÉES sont rendues (`bar_calendar.completed_series`) : une
semaine en cours n'est pas une bougie.
"""
from __future__ import annotations

import datetime
import json
import os
import pathlib
import sys
from typing import Callable

ROOT = pathlib.Path(__file__).resolve().parent.parent
if str(ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(ROOT / "scripts"))

import atomic_file  # noqa: E402  # type: ignore[import-not-found]
import bar_calendar  # noqa: E402  # type: ignore[import-not-found]
import prices_server  # noqa: E402  # type: ignore[import-not-found]

DEFAULT_URL = "https://wallet-prices.kakobaba1212.workers.dev"
MAX_AGE_S = 12 * 3600
WEEKS = 104

SeriesGetter = Callable[[str], bytes]


def server_getter(config: dict) -> tuple[SeriesGetter | None, str | None]:
    """La fonction qui lit une série sur notre serveur, ou l'erreur de réglage."""
    url = config.get("prices_url") or DEFAULT_URL
    key = config.get("prices_key")
    if not key and config.get("prices_key_file"):
        try:
            key = pathlib.Path(config["prices_key_file"]).expanduser().read_text(encoding="utf-8").strip()
        except OSError as error:
            return None, f"price server key unreadable ({error.__class__.__name__})"
    if not url or not key:
        return None, ("no price server key (prices_key in client.json): run "
                      "`python3 wallet_mcp/install_client.py` again, it obtains one by itself")
    client = prices_server.Client(url.rstrip("/"), key)
    return client.get_series, None


def series(conid: int, folder: pathlib.Path, getter: SeriesGetter,
           now: datetime.datetime) -> dict:
    """La série d'un conid : `{"series": …, "stale_error": …}` ou `{"error": …}`."""
    path = folder / f"{conid}.json"
    fresh = path.exists() and (now.timestamp() - path.stat().st_mtime) < MAX_AGE_S
    stale_error = None
    if not fresh:
        try:
            payload = getter(f"{conid}.json")
            json.loads(payload)
            atomic_file.write_text(path, payload.decode("utf-8"))
            # L'âge se mesure sur l'horloge de l'appelant, pas sur celle du disque :
            # un test au temps figé lirait sinon une copie « du futur » comme fraîche.
            os.utime(path, (now.timestamp(), now.timestamp()))
        except prices_server.ServerError as error:
            stale_error = str(error)
        except (ValueError, UnicodeDecodeError):
            stale_error = "the server returned an unreadable series"
    if not path.exists():
        if stale_error and "HTTP 404" in stale_error:
            return {"error": "no series on our server for this holding (not collected yet)"}
        return {"error": f"series unavailable: {stale_error}"}
    return {"series": json.loads(path.read_text(encoding="utf-8")), "stale_error": stale_error}


def settled_weeks(data: dict, today: datetime.date, weeks: int = WEEKS) -> list[dict]:
    """Les `weeks` dernières bougies hebdomadaires RÉGLÉES, datées."""
    bars = (data.get("bars") or {}).get("1W") or {}
    settled = {stamp for stamp, _ in bar_calendar.completed_series(bars, "1W", as_of=today)}
    rows = []
    for index, stamp in enumerate(bars.get("t", [])):
        if stamp not in settled:
            continue
        values = {key: (bars.get(key) or [None] * (index + 1))[index] for key in ("o", "h", "l", "c")}
        if None in values.values() or values["c"] <= 0:
            continue
        rows.append({"week": stamp[:10], **values})
    return rows[-weeks:]
