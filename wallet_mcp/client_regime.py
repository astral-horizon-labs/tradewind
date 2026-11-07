"""Les alertes de régime de la méthode, évaluées pour un client sur nos prix.

POURQUOI (2026-11-07, décision du propriétaire, lot 4 du MCP client). Les alertes de
régime disent si le marché porte encore un pari : la biotech mène-t-elle, le crédit
tient-il, la peur monte-t-elle. Ce sont des données de MARCHÉ pures : on les sert
sans rien savoir du compte du client.

UNE SEULE LOI. Les alertes sont celles que livre la méthode
(`references/tripwires-method.json`), les conids ceux de la graine de marché
(`universe_seed_file`), l'évaluation celle de `tripwires.check`, sur les clôtures
RÉGLÉES des séries que notre serveur sert au client. Une alerte corrigée dans la
méthode l'est pour lui le même jour.

UNE ALERTE SE LIT, ELLE NE SE RÉCITE PAS. Elle juge une clôture contre une moyenne :
elle retarde par construction. Chaque alerte rend donc ses dernières valeurs réglées
et le SENS du mouvement face à son seuil (`direction`), pour que l'assistant dise
où va le marché plutôt que « c'est rouge ».

Ce qui n'est pas servi : l'alerte `book` (baisse du livre depuis son sommet), qui
exige l'historique de la valeur du compte, absent du rapport Flex de positions.
"""
from __future__ import annotations

import datetime
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
for folder in (ROOT / "scripts", pathlib.Path(__file__).resolve().parent):
    if str(folder) not in sys.path:
        sys.path.insert(0, str(folder))

import client_book  # noqa: E402
import client_messages  # noqa: E402
import client_prices  # noqa: E402
import data_root  # noqa: E402  # type: ignore[import-not-found]
import price_cache  # noqa: E402  # type: ignore[import-not-found]
import tripwires  # noqa: E402  # type: ignore[import-not-found]

METHOD_FILE = ROOT / "references" / data_root.TRIPWIRES_SEED_NAME
#: Le texte public, en anglais, de chaque alerte de la méthode (2026-11-07, produit
#: public Tradewind). La méthode reste française pour le propriétaire ; une alerte sans
#: traduction fait échouer `tests/test_wallet_mcp_client.py`.
ENGLISH_FILE = pathlib.Path(__file__).resolve().parent / "alerts_en.json"
RECENT = 4
STATUS_WORDS = {"TRIGGERED": "triggered", "armed": "armed", "UNVERIFIABLE": "unverifiable"}


def method_alerts() -> list[dict]:
    return json.loads(METHOD_FILE.read_text(encoding="utf-8"))["tripwires"]


def symbols_of(alert: dict) -> set[str]:
    names = [alert.get(key) for key in ("num", "den", "symbol")]
    names += [leg[key] for leg in alert.get("legs") or [] for key in ("num", "den")]
    return {name for name in names if name}


def direction(alert: dict, values: list[float]) -> str | None:
    """Le sens du mouvement face au SEUIL, sur les dernières clôtures réglées.

    Neutre à dessein : une alerte de reprise (`smh-reprise`) est une bonne nouvelle
    quand elle franchit, une alerte de rupture une mauvaise. « se rapproche du seuil »
    sur une alerte franchie dit qu'elle se lève ; sur une alerte non franchie, qu'elle
    approche. Une valeur passée de l'autre côté sur la période « a traversé le seuil ».
    Un écart de moins d'un pour cent du seuil se lit « stable ».
    """
    if len(values) < 2:
        return None
    threshold = alert.get("below", alert.get("above"))
    if not isinstance(threshold, (int, float)) or not threshold:
        return None
    if (values[0] - threshold) * (values[-1] - threshold) < 0:
        return "crossed the threshold"
    before, after = abs(values[0] - threshold), abs(values[-1] - threshold)
    if abs(after - before) < abs(threshold) * 0.01:
        return "steady"
    return "nearing the threshold" if after < before else "moving away from the threshold"


def regime_alerts(getter=None, *, now: datetime.datetime | None = None) -> dict:
    now = now or client_book.now_utc()
    if getter is None:
        getter, error = client_prices.server_getter(client_book.read_config()[0] or {})
        if error:
            return {"error": error}
    english = json.loads(ENGLISH_FILE.read_text(encoding="utf-8"))
    alerts = [alert for alert in method_alerts() if alert["kind"] != "book"]
    seed = json.loads(data_root.universe_seed_file().read_text(encoding="utf-8"))["instruments"]
    folder = client_book.state_dir() / "series"
    universe, notes = {}, []
    for symbol in sorted(set().union(*(symbols_of(alert) for alert in alerts))):
        conid = seed[symbol]["conid"]
        found = client_prices.series(conid, folder, getter, now)
        if "error" in found:
            notes.append(f"{symbol}: {found['error']}")
            continue
        if found.get("stale_error"):
            notes.append(f"{symbol}: keeping the cached series, {found['stale_error']}")
        universe[symbol] = {"conid": conid}
    # La loi lit le cache par `price_cache.CACHE_DIR` : celui du client, le seul que
    # ce processus sert.
    price_cache.CACHE_DIR = folder
    rows = []
    for alert in alerts:
        if not symbols_of(alert) <= set(universe):
            status, line = "UNVERIFIABLE", "series missing on the price server"
        else:
            status, line = tripwires.check(alert, universe)
        value, as_of, _, why = (tripwires.topic_value(alert, universe)
                                if status != "UNVERIFIABLE" else (None, None, None, line))
        recent = []
        if status != "UNVERIFIABLE" and alert["kind"] in ("close", "ratio"):
            recent = [round(v, 4) for v in tripwires.recent_values(alert, universe, RECENT)]
        text = english.get(alert["id"], {})
        as_of = client_messages.english(str(as_of)) if as_of else None
        rows.append({
            "id": alert["id"], "label": text.get("label"), "status": STATUS_WORDS.get(status, status),
            "value": round(value, 4) if isinstance(value, (int, float)) else value,
            "threshold": {"below": alert["below"]} if "below" in alert else {"above": alert.get("above")},
            "settled": as_of.split(" — ")[0] if as_of else None,
            "detail": as_of.split(" — ", 1)[1] if as_of and " — " in as_of else None,
            "recent_settled": recent,
            "direction": direction(alert, recent),
            "release_closes": alert.get("release_closes", 1),
            "meaning": text.get("meaning"), "on_trigger": text.get("action"),
            "touches": text.get("exposure_note"),
            **({"why": client_messages.english(why or line)} if status == "UNVERIFIABLE" else {}),
        })
    order = {"triggered": 0, "unverifiable": 1, "armed": 2}
    rows.sort(key=lambda row: order.get(row["status"], 3))
    return {"evaluated_on": now.date().isoformat(), "alerts": rows, "notes": notes,
            "reading": ("an alert lags by construction: first say where the move is heading (`direction`) "
                        "and what it changes for the affected holdings, never \"everything is red\"")}
