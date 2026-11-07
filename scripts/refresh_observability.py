#!/usr/bin/env python3
"""État durable et corrélation des passes de rafraîchissement de clôtures."""
from __future__ import annotations

import datetime
import contextlib
import email.utils
import fcntl
import json
import math
import pathlib
import atomic_file
import time
import uuid

HERE = pathlib.Path(__file__).resolve().parent
SKILL = HERE.parent
import data_root
PRICE_DATA = data_root.price_logs_dir()
GLOBAL_CIRCUIT = PRICE_DATA / "market-history-global-circuit.json"
COLLECTION_LOCK = SKILL / "data" / "history-collection.lock"
SESSION_RETRY_DELAY = datetime.timedelta(minutes=15)
PASS_EVENTS = PRICE_DATA / "price-refresh-passes.jsonl"
DIAGNOSTICS = PRICE_DATA / "price-refresh-diagnostics.jsonl"
GLOBAL_DELAYS = {
    429: datetime.timedelta(minutes=15),
    503: datetime.timedelta(minutes=5),
}
BASE_REQUEST_INTERVAL_SECONDS = 4
MAX_REQUEST_INTERVAL_SECONDS = 60
RECOVERY_SUCCESS_COUNT = 5
ADAPTIVE_RELAX_THRESHOLD_SECONDS = 10
SERVICE_CONFIRMATION_DISTINCT_CONIDS = 2
BASKET_INITIAL_PROBE_BUDGET = 3
BASKET_MAX_PROBE_BUDGET = 5
BASKET_PROBE_RECOVERY_SUCCESSES = 2
BASKET_PROBE_DELAY = datetime.timedelta(hours=6)
BASKET_DURABLE_REVALIDATION_DELAY = datetime.timedelta(days=7)
BASKET_QUARANTINE_REVALIDATION_DELAY = datetime.timedelta(days=14)
BASKET_DURABLE_AFTER_PROBES = 3


@contextlib.contextmanager
def history_collection_lock(path=None):
    """Une seule collecte par checkout, lancement manuel et launchd compris."""
    destination = path or COLLECTION_LOCK
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("a") as handle:
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            yield False
            return
        try:
            yield True
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


class HistoryCircuitOpen(RuntimeError):
    """Une autre collecte a ouvert la pause pendant l'attente de cadence."""

    def __init__(self, circuit):
        super().__init__(circuit["reason"])
        self.circuit = circuit


def global_failure_kind(metadata):
    """Une session absente n'est jamais un défaut propre à un instrument."""
    status = metadata.get("http_status")
    reason = str(metadata.get("error") or "").lower()
    if status in {401, 403} or any(value in reason for value in (
            "not authenticated", "no session", "no bridge", "access denied")):
        return "session"
    return {429: "rate_limit", 503: "service"}.get(status)


def history_payload_served(metadata):
    """Vrai si la source a servi un historique exploitable, gardes mises à part."""
    return bool((metadata or {}).get("bars_served"))


def service_failure_forces_global(metadata):
    """Un ``Retry-After`` porté par un 503 annonce lui-même le repos global."""
    return retry_after_seconds((metadata or {}).get("response_headers")) is not None


class ServiceFailureConfirmation:
    """Confirme une panne de service (503) sur des contrats DISTINCTS."""

    def __init__(self, *, required=SERVICE_CONFIRMATION_DISTINCT_CONIDS):
        self.required = max(1, int(required))
        self._conids = []

    def observe_service_failure(self, conid, metadata=None):
        """Classe un 503 : ``global`` s'il est confirmé, sinon ``isolated``."""
        if retry_after_seconds((metadata or {}).get("response_headers")) is not None:
            return "global"
        key = str(conid)
        if key not in self._conids:
            self._conids.append(key)
        return "global" if len(self._conids) >= self.required else "isolated"

    def record_success(self):
        """Un payload historique servi efface les échecs restés provisoires."""
        self._conids.clear()


class GatewayRequestPacer:
    """Espace les départs réels Gateway depuis le même repère monotone."""

    def __init__(self, *, min_interval=BASE_REQUEST_INTERVAL_SECONDS,
                 monotonic=None, sleep=None):
        self.min_interval = max(0.0, float(min_interval))
        self.monotonic = monotonic or time.monotonic
        self.sleep = sleep or time.sleep
        self.last_started_at = None
        self.waited_seconds = 0.0

    def wait_seconds(self):
        """Attente restante avant le prochain départ, sans l'effectuer."""
        if self.last_started_at is None:
            return 0.0
        return max(0.0, self.last_started_at + self.min_interval - self.monotonic())

    def before_request(self):
        """Attend jusqu'au départ autorisé puis retourne l'attente réellement subie."""
        before = self.monotonic()
        while (remaining := self.wait_seconds()) > 0:
            self.sleep(remaining)
        self.last_started_at = self.monotonic()
        waited = max(0.0, self.last_started_at - before)
        self.waited_seconds += waited
        return waited
DIAGNOSTIC_MAX_RECORDS = 200
DIAGNOSTIC_MAX_BYTES = 1_000_000
DIAGNOSTIC_FIELD_MAX_CHARS = 250_000


def utc_now():
    return datetime.datetime.now(datetime.timezone.utc)


def normalize_time(value=None):
    current = value or utc_now()
    if current.tzinfo is None:
        current = current.replace(tzinfo=datetime.timezone.utc)
    return current.astimezone(datetime.timezone.utc)


def new_pass_id(at=None):
    """Identifiant chronologique lisible, unique sans donnée de portefeuille."""
    current = normalize_time(at)
    stamp = current.strftime("%Y%m%dT%H%M%SZ")
    return f"{stamp}-{uuid.uuid4().hex[:8]}"


def _json_object(path):
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def _write_json(path, payload):

    atomic_file.write_text(path, json.dumps(payload, ensure_ascii=False, indent=2) + "\n")




TRANSPORT_FAILURE_MARKERS = ("urlerror", "timeouterror", "timed out", "ssl:",
                             "connection refused", "connection reset",
                             "remote end closed", "eof occurred")


def is_transport_failure(reason):
    """Vrai si l'échec est un échec réseau, pas une réponse de la source."""
    text = str(reason or "").lower()
    return any(marker in text for marker in TRANSPORT_FAILURE_MARKERS)


def basket_retry_category(reason, *, previous=None):
    """Classe une indisponibilité sans jamais la confondre avec une série stale."""
    text = str(reason or "").lower()
    if "market data permissions" in text:
        return "history_durable"
    if "contract details" in text or "contrat" in text:
        return "contract_quarantine"
    if isinstance(previous, dict) and previous.get("category") == "history_durable":
        return "history_durable"
    return "history_probe"


def basket_retry_delay(category):
    """Cadence explicite par cause ; aucune dépendance à l'ouverture US."""
    return {
        "history_probe": BASKET_PROBE_DELAY,
        "history_durable": BASKET_DURABLE_REVALIDATION_DELAY,
        "contract_quarantine": BASKET_QUARANTINE_REVALIDATION_DELAY,
        "bridge_quarantine": BASKET_QUARANTINE_REVALIDATION_DELAY,
    }.get(category, BASKET_PROBE_DELAY)


def next_basket_retry(previous, *, reason, at=None):
    """Construit l'état de reprise, de quarantaine ou de révalidation lente."""
    observed = normalize_time(at)
    previous = previous if isinstance(previous, dict) else {}
    category = basket_retry_category(reason, previous=previous)
    probe_count = int(previous.get("probe_count") or 0)
    if category == "history_probe":
        probe_count += 1
        if probe_count >= BASKET_DURABLE_AFTER_PROBES:
            category = "history_durable"
    next_at = observed + basket_retry_delay(category)
    return {
        "category": category,
        "reason": str(reason),
        "observed_at": observed.isoformat(),
        "retry_at": next_at.isoformat(),
        "next_action": "probe" if category == "history_probe" else "revalidation",
        "probe_count": probe_count,
        "last_probe_at": observed.isoformat(),
    }


def basket_probe_budget(policy):
    """Budget borné et durable ; un fichier ancien démarre prudemment à trois."""
    try:
        value = int((policy or {}).get("probe_budget"))
    except (TypeError, ValueError):
        value = BASKET_INITIAL_PROBE_BUDGET
    return min(BASKET_MAX_PROBE_BUDGET, max(1, value))


def record_basket_probe_success(policy, *, at=None):
    """Relâche graduellement le budget après des preuves de disponibilité."""
    result = dict(policy or {})
    successes = int(result.get("recovery_successes") or 0) + 1
    budget = basket_probe_budget(result)
    if successes >= BASKET_PROBE_RECOVERY_SUCCESSES and budget < BASKET_MAX_PROBE_BUDGET:
        budget += 1
        successes = 0
    result.update({
        "probe_budget": budget,
        "recovery_successes": successes,
        "last_success_at": normalize_time(at).isoformat(),
    })
    return result


def basket_retry_plan(pending, policy=None, *, at=None):
    """Sélectionne peu de tentatives, diversifiées et entièrement déterministes."""
    now = normalize_time(at)
    due = []
    for key, entry in (pending or {}).items():
        if not isinstance(entry, dict):
            continue
        value = entry.get("retry_at")
        try:
            retry_at = datetime.datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        except ValueError:
            retry_at = now
        if retry_at.tzinfo is None:
            retry_at = retry_at.replace(tzinfo=datetime.timezone.utc)
        if retry_at <= now:
            due.append((str(key), entry))
    def category(entry):
        value = entry.get("category")
        return value if isinstance(value, str) else basket_retry_category(entry.get("reason"))







    transport = [(key, entry) for key, entry in due
                 if category(entry) == "history_probe" and is_transport_failure(entry.get("reason"))]
    transport_keys = {key for key, _ in transport}
    probes = [(key, entry) for key, entry in due
              if category(entry) == "history_probe" and key not in transport_keys]
    revalidations = [(key, entry) for key, entry in due if category(entry) in {
        "history_durable", "contract_quarantine", "bridge_quarantine"}]

    def sort_key(item):
        key, entry = item
        return (int(entry.get("probe_count") or 0), str(entry.get("last_probe_at") or ""),
                str(entry.get("exchange") or ""), str(entry.get("reason") or ""), key)

    selected = []
    seen_sources = set()
    for item in sorted(probes, key=sort_key):
        source = (str(item[1].get("exchange") or ""), str(item[1].get("reason") or ""))
        if source not in seen_sources:
            selected.append((item[0], item[1], "probe"))
            seen_sources.add(source)
        if len(selected) >= basket_probe_budget(policy):
            break
    if len(selected) < basket_probe_budget(policy):
        selected_keys = {key for key, _, _ in selected}
        for key, entry in sorted(probes, key=sort_key):
            if key not in selected_keys:
                selected.append((key, entry, "probe"))
            if len(selected) >= basket_probe_budget(policy):
                break
    if revalidations:
        key, entry = sorted(revalidations, key=sort_key)[0]
        selected.append((key, entry, "revalidation"))
    selected.extend((key, entry, "probe") for key, entry in sorted(transport, key=sort_key))
    return selected


def active_global_circuit(at=None, path=None):
    """Circuit encore ouvert, ou None sans modifier le fichier durable."""
    payload = _json_object(path or GLOBAL_CIRCUIT)
    if payload.get("state") != "open" or payload.get("scope") != "global":
        return None
    retry_at = payload.get("retry_at")
    if not isinstance(retry_at, str):
        return None
    try:
        due = datetime.datetime.fromisoformat(retry_at.replace("Z", "+00:00"))
    except ValueError:
        return None
    if due.tzinfo is None:
        due = due.replace(tzinfo=datetime.timezone.utc)
    return payload if normalize_time(at) < due else None


def retry_after_seconds(headers, *, at=None):
    """Lit Retry-After sans jamais laisser un en-tête invalide raccourcir le repos."""
    if not isinstance(headers, dict):
        return None
    value = next((item for key, item in headers.items()
                  if str(key).lower() == "retry-after"), None)
    if not isinstance(value, str):
        return None
    try:
        seconds = int(value.strip())
    except ValueError:
        try:
            retry_at = email.utils.parsedate_to_datetime(value)
        except (TypeError, ValueError):
            return None
        if retry_at.tzinfo is None:
            retry_at = retry_at.replace(tzinfo=datetime.timezone.utc)
        seconds = int((retry_at.astimezone(datetime.timezone.utc) - normalize_time(at)).total_seconds())
    return seconds if seconds > 0 else None


def adaptive_request_interval(at=None, path=None):
    """Cadence renforcée conservée après un refus global, sinon None."""
    payload = _json_object(path or GLOBAL_CIRCUIT)
    if payload.get("scope") != "global" or not (
            payload.get("http_status") in GLOBAL_DELAYS or payload.get("failure_kind") == "session"):
        return None
    value = payload.get("request_interval_seconds")
    try:
        interval = int(value)
    except (TypeError, ValueError):


        interval = BASE_REQUEST_INTERVAL_SECONDS * 2
    return min(MAX_REQUEST_INTERVAL_SECONDS, max(BASE_REQUEST_INTERVAL_SECONDS, interval))


def relax_request_interval(interval):
    """Relâche la cadence d'un palier après cinq succès, jamais sous la base."""
    interval = int(interval)
    if interval <= ADAPTIVE_RELAX_THRESHOLD_SECONDS:
        return max(BASE_REQUEST_INTERVAL_SECONDS, interval - 1)
    return max(ADAPTIVE_RELAX_THRESHOLD_SECONDS, math.ceil(interval * 0.75))


def record_global_success(*, at=None, path=None):
    """Relâche la cadence tous les cinq succès, sans jamais revenir par rafale."""
    destination = path or GLOBAL_CIRCUIT
    payload = _json_object(destination)
    if payload.get("state") == "closed":
        return payload
    interval = adaptive_request_interval(at, path=destination)
    if interval is None or active_global_circuit(at, path=destination):
        return payload or None
    successes = int(payload.get("recovery_successes") or 0) + 1
    if successes >= RECOVERY_SUCCESS_COUNT:
        interval = relax_request_interval(interval)
        successes = 0
    payload.update({
        "version": 2,
        "state": "closed" if interval == BASE_REQUEST_INTERVAL_SECONDS else "recovering",
        "request_interval_seconds": interval,
        "recovery_successes": successes,
        "last_success_at": normalize_time(at).isoformat(),
    })
    if interval == BASE_REQUEST_INTERVAL_SECONDS:
        payload["closed_at"] = normalize_time(at).isoformat()
    _write_json(destination, payload)
    return payload


def open_global_circuit(http_status, *, metadata=None, pass_id=None, run_id=None,
                        request_ordinal=None, at=None, path=None):
    """Ouvre le circuit pour une indisponibilité HTTP globale documentée."""
    metadata = metadata if isinstance(metadata, dict) else {}
    kind = global_failure_kind({**metadata, "http_status": http_status})
    if not kind:
        raise ValueError(f"statut HTTP non global : {http_status}")
    observed = normalize_time(at)
    destination = path or GLOBAL_CIRCUIT
    headers = metadata.get("response_headers") or {}
    retry_after = retry_after_seconds(headers, at=observed)
    delay = max(SESSION_RETRY_DELAY if kind == "session" else GLOBAL_DELAYS[http_status],
                datetime.timedelta(seconds=retry_after or 0))
    previous_interval = adaptive_request_interval(observed, path=destination)
    request_interval = min(
        MAX_REQUEST_INTERVAL_SECONDS,
        max(BASE_REQUEST_INTERVAL_SECONDS, previous_interval or BASE_REQUEST_INTERVAL_SECONDS) * 2,
    )
    if kind == "session":
        request_interval = previous_interval or BASE_REQUEST_INTERVAL_SECONDS
    payload = {
        "version": 2,
        "state": "open",
        "scope": "global",
        "failure_kind": kind,
        "http_status": http_status,
        "reason": ("session ou bridge Gateway indisponible : "
                   + str(metadata.get("error") or f"HTTP {http_status}")
                   if kind == "session" else
                   f"service historique IBKR temporairement indisponible (HTTP {http_status})"),
        "opened_at": observed.isoformat(),
        "retry_at": (observed + delay).isoformat(),
        "retry_after_seconds": retry_after,
        "retry_after_source": "header" if retry_after is not None else "policy",
        "request_interval_seconds": request_interval,
        "recovery_successes": 0,
        "pass_id": pass_id,
        "run_id": run_id,
        "request_ordinal": request_ordinal,
        "response_headers": headers,
    }
    _write_json(destination, payload)
    return payload


def append_pass_event(event, pass_id, *, path=None, at=None, **detail):
    """Ajoute une borne parent durable, commune aux travaux enfants."""
    record = {
        "version": 1,
        "at": normalize_time(at).isoformat(),
        "event": event,
        "pass_id": pass_id,
        **detail,
    }
    destination = path or PASS_EVENTS
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n")
    return record


def record_diagnostic(*, pass_id, stage, detail, path=None, at=None, **context):
    """Conserve l'erreur complète dans un journal local volontairement borné."""
    def bounded(value):
        if not isinstance(value, str) or len(value) <= DIAGNOSTIC_FIELD_MAX_CHARS:
            return value
        removed = len(value) - DIAGNOSTIC_FIELD_MAX_CHARS
        return value[:DIAGNOSTIC_FIELD_MAX_CHARS] + \
            f"\n[… {removed} caractère(s) au-delà de la borne locale]"

    record = {
        "version": 1,
        "at": normalize_time(at).isoformat(),
        "pass_id": pass_id,
        "stage": stage,
        "detail": bounded(str(detail)),
        **{key: bounded(value) for key, value in context.items()},
    }
    destination = path or DIAGNOSTICS
    records = []
    try:
        for line in destination.read_text(encoding="utf-8").splitlines():
            try:
                value = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(value, dict):
                records.append(value)
    except OSError:
        pass
    records.append(record)
    records = records[-DIAGNOSTIC_MAX_RECORDS:]
    encoded = [json.dumps(item, ensure_ascii=False, separators=(",", ":"))
               for item in records]
    while len(encoded) > 1 and sum(len(line.encode("utf-8")) + 1 for line in encoded) \
            > DIAGNOSTIC_MAX_BYTES:
        encoded.pop(0)
    atomic_file.write_text(destination, "\n".join(encoded) + "\n")
    return record
