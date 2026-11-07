#!/usr/bin/env python3
"""Le magasin des prix `data/prices/` : emplacement, lecture mémoïsée, écriture
atomique et loi de fusion des barres."""
from __future__ import annotations
import copy, json, pathlib, os, tempfile, threading
from collections import namedtuple
from derived_cache import DerivedCache, file_signature
from bar_calendar import bar_period, period_end

HERE = pathlib.Path(__file__).resolve().parent
SKILL = HERE.parent
import data_root

CACHE_DIR = data_root.prices_dir()



def cache_file(conid):
    return CACHE_DIR / f"{conid}.json"

























PRICE_READ_CACHE_MAX_ENTRIES = 1024
_BAR_LISTS = ("t", "c", "h", "l", "o")
_PRICE_SCALAR_TYPES = frozenset({str, int, float, bool, type(None)})

_PriceEntry = namedtuple("_PriceEntry", "payload flat")
_PRICE_CACHE_LOCK = threading.Lock()
_PRICE_CACHE = None


def _price_cache():
    """Le cache partagé, construit UNE fois — y compris sous démarrage froid."""
    global _PRICE_CACHE
    if _PRICE_CACHE is None:
        with _PRICE_CACHE_LOCK:
            if _PRICE_CACHE is None:
                _PRICE_CACHE = DerivedCache(max_entries=PRICE_READ_CACHE_MAX_ENTRIES,
                                            copy_value=_copy_price_entry)
    return _PRICE_CACHE


def _price_payload_is_flat(payload):
    """Vrai si les listes connues ne portent que des scalaires immuables."""
    bars = payload.get("bars") if isinstance(payload, dict) else None
    if not isinstance(bars, dict):
        return False
    for bar in bars.values():
        if not isinstance(bar, dict):
            continue
        for key in _BAR_LISTS:
            value = bar.get(key)
            if isinstance(value, list) and set(map(type, value)) - _PRICE_SCALAR_TYPES:
                return False
    return True


def _copy_price_value(value):
    """Copie d'une valeur de forme inattendue : jamais le cas d'un fichier de prix."""
    if isinstance(value, list):
        return [_copy_price_value(item) for item in value]
    if isinstance(value, dict):
        return {key: _copy_price_value(item) for key, item in value.items()}
    return copy.deepcopy(value)


def _copy_bar(bar):
    """Les listes parallèles d'une barre sont copiées en bloc, le reste une fois."""
    if not isinstance(bar, dict):
        return _copy_price_value(bar)
    out = dict(bar)
    for key, value in out.items():
        if key in _BAR_LISTS and isinstance(value, list):
            out[key] = list(value)
        elif isinstance(value, (list, dict)):
            out[key] = _copy_price_value(value)
    return out


def _copy_price_payload(payload):
    """Copie bornée à la forme connue des fichiers de prix."""
    if not isinstance(payload, dict):
        return _copy_price_value(payload)
    out = dict(payload)
    bars = out.get("bars")
    if isinstance(bars, dict):
        out["bars"] = {key: _copy_bar(bar) for key, bar in bars.items()}
    for key, value in out.items():
        if key != "bars" and isinstance(value, (list, dict)):
            out[key] = _copy_price_value(value)
    return out


def _copy_price_entry(entry):
    """Copie d'une entrée : par tranche si sa forme est plate, profonde sinon."""
    if entry.flat:
        return _PriceEntry(_copy_price_payload(entry.payload), True)
    return _PriceEntry(copy.deepcopy(entry.payload), False)


def _price_version(path):
    """Signature partagée du fichier ; une racine qui est un FICHIER vaut absence."""
    try:
        return file_signature(path)
    except NotADirectoryError:
        return (str(pathlib.Path(path).resolve()), None)


def _read_price_entry(path):
    """Décodage direct : l'absence est une VALEUR, l'illisible reste une erreur."""
    payload = json.loads(path.read_text()) if path.exists() else None
    return _PriceEntry(payload, _price_payload_is_flat(payload))


def read_cache(conid, cache=None):
    """Le contenu du fichier de prix, mémoïsé tant que sa génération n'a pas changé."""
    path = pathlib.Path(cache) / f"{conid}.json" if cache is not None else cache_file(conid)
    return _price_cache().get(lambda: _price_version(path),
                              lambda: _read_price_entry(path)).payload


def price_cache_info():
    """Les mesures locales de la mémoïsation, sans changer le contrat des lecteurs."""
    return _price_cache().info()


def clear_price_cache():
    """Vide la mémoire et ses compteurs : lecture directe, comparaison, tests."""
    global _PRICE_CACHE
    with _PRICE_CACHE_LOCK:
        _PRICE_CACHE = None


SEALED_REGISTRY = SKILL / "references" / "basket-contracts.json"


def sealed_archive(conid, cache_dir=None):
    """Vrai si ce conid est une archive de panier scellée par son empreinte."""
    directory = pathlib.Path(cache_dir or CACHE_DIR)
    if directory.resolve() != data_root.series_store().resolve():
        return False
    try:
        registry = json.loads(SEALED_REGISTRY.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False
    change = registry.get(str(conid)) if isinstance(registry, dict) else None
    return isinstance(change, dict) and bool(change.get("archive_sha256"))


def write_cache(conid, obj, before_publish=None):
    """Publie un JSON complet : les lecteurs restent libres pendant la collecte."""
    if sealed_archive(conid):
        raise ValueError(f"archive scellée {conid} : le rescellement passe par "
                         "references/basket-contracts.json, jamais par une collecte")
    encoded = json.dumps(obj, ensure_ascii=False)
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=CACHE_DIR,
                                     prefix=f".{conid}.", suffix=".tmp", delete=False) as handle:
        temporary = pathlib.Path(handle.name)
        try:
            handle.write(encoded)
            handle.flush()


            os.fsync(handle.fileno())
        except BaseException:
            temporary.unlink(missing_ok=True)
            raise
    target = cache_file(conid)
    try:
        os.chmod(temporary, target.stat().st_mode & 0o777 if target.exists() else 0o644)


        if before_publish is not None:
            before_publish()
        os.replace(temporary, target)
    finally:
        temporary.unlink(missing_ok=True)



def price_tick(price):
    """Le plus petit écart de cotation plausible à ce niveau de prix."""
    return 0.005 if abs(price) < 0.5 else 0.01


def beyond_tolerance(reference, other, tolerance):
    """Vrai si deux clôtures s'écartent de plus de `tolerance` ET de plus d'un pas."""
    if not reference:
        return True
    gap = abs(other - reference)
    return gap / abs(reference) > tolerance and gap > price_tick(reference) + 1e-9


def merge_bars(old, t, c, bar, h=None, l=None, o=None, src=None, foreign_overwrites_ibkr=False,
               primary="ibkr"):
    """Union par PÉRIODE (semaine ISO en 1W, mois en 1M), la réponse entrante"""
    foreign = src if src not in (None, "ibkr") else None
    incoming = foreign or "ibkr"
    secondary = incoming != primary
    old_fetched = str((old or {}).get("settled_through") or (old or {}).get("fetched") or "")[:10]

    def settled_when_written(stamp):
        if not old_fetched:
            return True
        return old_fetched > period_end(stamp, bar).isoformat()

    m = {}
    if old:
        oh, ol, oo = old.get("h"), old.get("l"), old.get("o")
        marks = old.get("src") or {}
        for i, (ts, v) in enumerate(zip(old["t"], old["c"])):
            m[bar_period(ts, bar)] = (ts, v, oh[i] if oh else None,
                                     ol[i] if ol else None, oo[i] if oo else None,
                                     marks.get(ts))
    first = min(m) if m else None
    for i, (ts, v) in enumerate(zip(t, c)):
        period = bar_period(ts, bar)
        if secondary and first is not None:
            if period < first:
                continue
            held = m.get(period)
            if (held is not None and (held[5] or "ibkr") == primary
                    and not (foreign and foreign_overwrites_ibkr)
                    and settled_when_written(held[0])):
                continue
        if not foreign and foreign_overwrites_ibkr:
            held = m.get(period)
            if (held is not None and held[5] and held[5] != "ibkr"
                    and settled_when_written(held[0])):
                continue
        m[period] = (ts, v, h[i] if h else None,
                     l[i] if l else None, o[i] if o else None, foreign)
    rows = sorted(m.values(), key=lambda row: row[0])
    out = {"t": [r[0] for r in rows], "c": [r[1] for r in rows]}
    if any(r[2] is not None for r in rows):
        out["h"] = [r[2] for r in rows]
    if any(r[3] is not None for r in rows):
        out["l"] = [r[3] for r in rows]
    if any(r[4] is not None for r in rows):
        out["o"] = [r[4] for r in rows]
    if any(r[5] for r in rows):
        out["src"] = {r[0]: r[5] for r in rows if r[5]}
    return out
