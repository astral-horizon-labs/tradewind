#!/usr/bin/env python3
"""Copie distante du cache de prix sur le serveur privé (phase P5, 2026-10-30)."""
from __future__ import annotations

import argparse
import concurrent.futures
import datetime
import hashlib
import io
import json
import os
import pathlib
import re
import sys
import tarfile
import urllib.error
import urllib.request

import atomic_file
import data_root

SERIES_NAME = re.compile(r"^\d{1,12}\.json$")


SNAPSHOT_EVERY_DAYS = 7
WORKERS = 8
TIMEOUT = 60

MARKET_PATH = "/v1/market/baskets.json"


class ServerError(RuntimeError):
    """Réponse refusée ou injoignable : rendue comme valeur par les commandes."""

    def __init__(self, message, *, status=None, code=None):
        super().__init__(message)
        self.status, self.code = status, code


def settings():
    """(url, clé) du serveur, ou None s'il n'est pas réglé sur ce poste."""
    value = data_root._local_config().get("prices_server")
    if not isinstance(value, dict) or not value.get("url") or not value.get("key_file"):
        return None
    key_path = pathlib.Path(str(value["key_file"])).expanduser()
    try:
        key = key_path.read_text(encoding="utf-8").strip()
    except OSError:
        return None
    return str(value["url"]).rstrip("/"), key


ROLES = ("publisher", "replica")


def role():
    """`publisher` (le poste qui collecte, défaut) ou `replica` (second poste)."""
    value = data_root._local_config().get("prices_server")
    chosen = value.get("role") if isinstance(value, dict) else None
    return chosen if chosen in ROLES else "publisher"


class Client:
    def __init__(self, url, key, opener=urllib.request.urlopen):
        self.url, self._key, self._open = url, key, opener

    def _request(self, method, path, body=None, sha256=None):
        headers = {"Authorization": f"Bearer {self._key}", "User-Agent": "wallet-prices/1"}
        if sha256:
            headers["X-Content-Sha256"] = sha256
        request = urllib.request.Request(self.url + path, data=body, method=method, headers=headers)
        try:
            with self._open(request, timeout=TIMEOUT) as response:
                return response.read()
        except urllib.error.HTTPError as error:
            detail = error.read().decode("utf-8", "replace")[:200]
            try:
                body = json.loads(detail)
            except ValueError:
                body = None
            code = body.get("code") if isinstance(body, dict) else None
            text = body.get("error") if isinstance(body, dict) and body.get("error") else detail
            raise ServerError(f"{method} {path} — HTTP {error.code} {text}",
                              status=error.code, code=code) from None
        except (urllib.error.URLError, TimeoutError, OSError) as error:
            raise ServerError(f"{method} {path} — serveur injoignable ({error})") from None

    def manifest(self):
        return json.loads(self._request("GET", "/v1/manifest"))

    def put_series(self, name, payload):
        self._request("PUT", f"/v1/series/{name}", payload, hashlib.sha256(payload).hexdigest())

    def get_series(self, name):
        return self._request("GET", f"/v1/series/{name}")

    def put_snapshot(self, payload):
        self._request("PUT", "/v1/snapshot", payload, hashlib.sha256(payload).hexdigest())

    def get_snapshot(self):
        return self._request("GET", "/v1/snapshot")

    def put_market(self, payload):
        self._request("PUT", MARKET_PATH, payload, hashlib.sha256(payload).hexdigest())

    def get_market(self):
        return self._request("GET", MARKET_PATH)


def local_series(directory=None):
    """{nom: (chemin, sha256)} des séries locales, rien d'autre que `{conid}.json`."""
    directory = pathlib.Path(directory or data_root.prices_dir())
    found = {}
    for path in sorted(directory.glob("*.json")):
        if SERIES_NAME.match(path.name):
            found[path.name] = (path, hashlib.sha256(path.read_bytes()).hexdigest())
    return found


def _differences(local, remote):
    """(à envoyer, à rapatrier) : séries absentes ou d'empreinte différente."""
    outgoing = [name for name, (_, sha) in local.items()
                if (remote.get(name) or {}).get("sha256") != sha]
    incoming = [name for name, entry in remote.items()
                if SERIES_NAME.match(name) and (name not in local
                                                or local[name][1] != entry.get("sha256"))]
    return outgoing, incoming


def snapshot_bytes(local):
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w:gz") as archive:
        for name, (path, _) in sorted(local.items()):
            archive.add(path, arcname=name)
    return buffer.getvalue()


def _snapshot_due(manifest, today):
    snapshot = manifest.get("snapshot") or {}
    uploaded = str(snapshot.get("uploaded") or "")[:10]
    if not uploaded:
        return True
    return today >= datetime.date.fromisoformat(uploaded) + datetime.timedelta(days=SNAPSHOT_EVERY_DAYS)


def publish(client=None, *, directory=None, snapshot=None, today=None):
    """Envoie les séries changées, et l'instantané s'il est dû. Rend une phrase,"""
    if client is None:


        real = data_root.series_store().resolve()
        if pathlib.Path(directory or data_root.prices_dir()).resolve() != real:
            return "cache isolé : aucune publication"
        if role() == "replica":
            return "poste en réplique : aucune publication"
        found = settings()
        if found is None:
            return "serveur de prix non réglé : aucune publication"
        client = Client(*found)
    today = today or datetime.date.today()
    try:
        manifest = client.manifest()
        local = local_series(directory)
        outgoing, _ = _differences(local, manifest.get("series") or {})
        failures = []

        def send(name):
            try:
                client.put_series(name, local[name][0].read_bytes())
            except ServerError as error:
                failures.append(f"{name} : {error}")

        with concurrent.futures.ThreadPoolExecutor(WORKERS) as pool:
            list(pool.map(send, outgoing))
        sent_snapshot = False
        if snapshot or (snapshot is None and _snapshot_due(manifest, today)):
            client.put_snapshot(snapshot_bytes(local))
            sent_snapshot = True
    except ServerError as error:
        return f"PUBLICATION ÉCHOUÉE — {error}"
    market = publish_market(client, directory, today)
    text = (f"{len(outgoing) - len(failures)}/{len(outgoing)} série(s) publiée(s) sur {len(local)}"
            if outgoing else f"aucune série changée sur {len(local)}")
    if sent_snapshot:
        text += ", instantané republié"
    if failures:
        text += f" — {len(failures)} refus, dont {failures[0]}"
    if market:
        text += f", {market}"
    return text


def publish_market(client, directory, today):
    """Calcule et publie le classement des paniers (`market_ranking`) ; rend une phrase,"""
    import market_ranking

    ranking = market_ranking.build(pathlib.Path(directory or data_root.prices_dir()), today)
    if ranking is None:
        return ""
    try:
        client.put_market(json.dumps(ranking, ensure_ascii=False).encode("utf-8"))
    except ServerError as error:
        return f"classement des paniers REFUSÉ — {error}"
    return f"classement des {len(ranking['baskets'])} paniers publié (semaine du {ranking['last_settled_week']})"


def _lock():
    import refresh_observability
    return refresh_observability.history_collection_lock()


def pull(client=None, *, directory=None, lock=_lock, overwrite=None):
    """Rapatrie les séries absentes, et les différentes sur une réplique, sous le"""
    if overwrite is None:
        overwrite = role() == "replica"
    if client is None:
        found = settings()
        if found is None:
            return "serveur de prix non réglé : rien à rapatrier"
        client = Client(*found)
    directory = pathlib.Path(directory or data_root.prices_dir())
    with lock() as acquired:
        if acquired is False:
            return "collecte en cours : rapatriement différé"
        try:
            manifest = client.manifest()
            local = local_series(directory)
            remote = manifest.get("series") or {}
            _, incoming = _differences(local, remote)
            if not local and incoming and manifest.get("snapshot"):
                with tarfile.open(fileobj=io.BytesIO(client.get_snapshot()), mode="r:gz") as archive:
                    for member in archive.getmembers():
                        if member.isfile() and SERIES_NAME.match(member.name):
                            atomic_file.write_text(directory / member.name,
                                                   archive.extractfile(member).read().decode("utf-8"))
                local = local_series(directory)
                _, incoming = _differences(local, remote)
            if not overwrite:
                incoming = [name for name in incoming if name not in local]
            for name in incoming:
                payload = client.get_series(name)
                if hashlib.sha256(payload).hexdigest() != remote[name].get("sha256"):
                    raise ServerError(f"{name} : empreinte reçue différente du manifeste")
                atomic_file.write_text(directory / name, payload.decode("utf-8"))
        except ServerError as error:
            return f"RAPATRIEMENT ÉCHOUÉ — {error}"
    return f"{len(incoming)} série(s) rapatriée(s) ; {len(remote)} sur le serveur"


def sync(client=None, *, directory=None, lock=_lock):
    """L'étape du dashboard : (état, détail), état parmi ok, skip et error."""
    if client is None:
        found = settings()
        if found is None:
            return "skip", "serveur de prix non réglé"
        client = Client(*found)
    text = pull(client, directory=directory, lock=lock)
    if text.startswith("RAPATRIEMENT ÉCHOUÉ"):
        return "error", text
    if text.startswith("collecte en cours"):
        return "skip", text
    if role() == "replica":
        return "ok", text
    try:
        manifest = client.manifest()
    except ServerError as error:
        return "error", f"SERVEUR INJOIGNABLE — {error}"
    outgoing, _ = _differences(local_series(directory), manifest.get("series") or {})
    if outgoing:
        return "ok", f"{len(outgoing)} série(s) à publier à la prochaine collecte ; {text}"
    return "ok", f"serveur à jour ; {text}"


def status(client=None, *, directory=None):
    if client is None:
        found = settings()
        if found is None:
            return "serveur de prix non réglé"
        client = Client(*found)
    try:
        manifest = client.manifest()
    except ServerError as error:
        return f"SERVEUR INJOIGNABLE — {error}"
    local = local_series(directory)
    outgoing, incoming = _differences(local, manifest.get("series") or {})
    snapshot = (manifest.get("snapshot") or {}).get("uploaded") or "aucun"
    return (f"{len(local)} série(s) locales, {len(manifest.get('series') or {})} sur le serveur ; "
            f"{len(outgoing)} à publier, {len(incoming)} à rapatrier ; instantané : {snapshot}")


def main(argv=None):
    parser = argparse.ArgumentParser(description="Copie distante du cache de prix (serveur privé).")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("status", help="compare le cache local au serveur")
    publish_parser = sub.add_parser("publish", help="envoie les séries changées")
    publish_parser.add_argument("--snapshot", action="store_true",
                                help="republie aussi l'instantané compressé")
    sub.add_parser("pull", help="rapatrie les séries absentes ou différentes")
    args = parser.parse_args(argv)
    if args.command == "publish":
        text = publish(snapshot=True if args.snapshot else None)
    elif args.command == "pull":
        text = pull()
    else:
        text = status()
    print(text)
    return 1 if ("ÉCHOU" in text or "INJOIGNABLE" in text) else 0


if __name__ == "__main__":
    os.umask(0o022)
    sys.exit(main())
