#!/usr/bin/env python3
"""LA GRAMMAIRE DES DÉCISIONS — une seule, pour les trois chemins qui l'écrivent."""
from __future__ import annotations
import data_root

import datetime
import re

import sensor_ref
















HORIZONS = ("long", "short")






ROLE_ENGINE = "engine"
ROLE_BALLAST = "ballast"
ROLES = (ROLE_ENGINE, ROLE_BALLAST)

STATUS_ACTIVE = "active"
STATUS_DRAFT = "draft"
STATUS_DISMISSED = "dismissed"







STATUS_CLOSED = "closed"
STATUSES = (STATUS_ACTIVE, STATUS_DRAFT, STATUS_DISMISSED, STATUS_CLOSED)


METHOD_MEMORY = "memory"
METHOD_FIB = "fib"
METHOD_PIVOT = "pivot"
METHOD_ROUND = "round"
METHOD_FABER = "faber"
METHOD_NET = "net"
METHODS = (METHOD_MEMORY, METHOD_FIB, METHOD_PIVOT, METHOD_ROUND,
           METHOD_FABER, METHOD_NET)



STATUS_LABELS = {STATUS_ACTIVE: "actif — suivi",
                 STATUS_DRAFT: "préparée — à relire",
                 STATUS_DISMISSED: "écarté",
                 STATUS_CLOSED: "soldée — position vendue"}
METHOD_LABELS = {METHOD_MEMORY: "mémoire", METHOD_FIB: "fib", METHOD_PIVOT: "pivot",
                 METHOD_ROUND: "rond", METHOD_FABER: "faber", METHOD_NET: "filet"}
HORIZON_LABELS = {"long": "long", "short": "court"}
ROLE_LABELS = {ROLE_ENGINE: "moteur", ROLE_BALLAST: "ballast"}




SENSOR_LABELS = {"armed": "armé", "TRIGGERED": "DÉCLENCHÉ", "RETURNED": "revenu",
                 "dormant": "dormant", "UNVERIFIABLE": "INVÉRIFIABLE"}














EFFECT_EXIT = "exit"
EFFECT_TRIM = "trim"
EFFECT_ADD = "add"
EFFECT_WARN = "warn"
EFFECT_REVIEW = "review"
EFFECTS = (EFFECT_EXIT, EFFECT_TRIM, EFFECT_ADD, EFFECT_WARN, EFFECT_REVIEW)
EFFECT_LABELS = {EFFECT_EXIT: "sortie", EFFECT_TRIM: "allègement", EFFECT_ADD: "renfort",
                 EFFECT_WARN: "alerte", EFFECT_REVIEW: "revue"}


SET_BY_OWNER = "owner"
SET_BY_AGENT = "agent"
SET_BY = (SET_BY_OWNER, SET_BY_AGENT)
SET_BY_LABELS = {SET_BY_OWNER: ("" + data_root.owner_label() + ""), SET_BY_AGENT: "agent"}







MOMENT_URGENCY = "urgency"
MOMENT_FOMO = "fomo"
MOMENT_CALM = "calm"
MOMENT_STATES = (MOMENT_URGENCY, MOMENT_FOMO, MOMENT_CALM)
MOMENT_LABELS = {MOMENT_URGENCY: "urgence", MOMENT_FOMO: "peur de rater",
                 MOMENT_CALM: "sérénité"}
CONVICTION_MIN = 1
CONVICTION_MAX = 5





FILL_OPEN = "open"
FILL_ADD = "add"
FILL_TRIM = "trim"
FILL_EXIT = "exit"
FILL_ROLES = (FILL_OPEN, FILL_ADD, FILL_TRIM, FILL_EXIT)
FILL_ROLE_LABELS = {FILL_OPEN: "achat", FILL_ADD: "renfort", FILL_TRIM: "allègement",
                    FILL_EXIT: "vente"}












CRITERION_EVENT = "event"
CRITERION_CASH = "cash"
CRITERION_DILUTION = "dilution"
CRITERION_CUSTOM = "custom"
CRITERION_KINDS = (CRITERION_EVENT, CRITERION_CASH, CRITERION_DILUTION, CRITERION_CUSTOM)
CRITERION_KIND_LABELS = {CRITERION_EVENT: "événement", CRITERION_CASH: "trésorerie",
                         CRITERION_DILUTION: "dilution", CRITERION_CUSTOM: "propre à la ligne"}
PILLAR_ON_TRACK = "on_track"
PILLAR_BEHIND = "behind"
PILLAR_PENDING = "pending"
PILLAR_BROKEN = "broken"
PILLAR_STATUSES = (PILLAR_ON_TRACK, PILLAR_BEHIND, PILLAR_PENDING, PILLAR_BROKEN)
PILLAR_STATUS_LABELS = {PILLAR_ON_TRACK: "en route", PILLAR_BEHIND: "en retard",
                        PILLAR_PENDING: "en attente", PILLAR_BROKEN: "rompu"}
PILLAR_MIN = 1
PILLAR_MAX = 5
CRITERION_FIELDS = ("id", "kind", "expect", "by", "threshold", "if_missed", "sensor")
PILLAR_FIELDS = ("id", "pillar", "expect", "status", "sensor", "by")















LIKELIHOOD_HIGH = "high"
LIKELIHOOD_MEDIUM = "medium"
LIKELIHOOD_LOW = "low"
LIKELIHOODS = (LIKELIHOOD_HIGH, LIKELIHOOD_MEDIUM, LIKELIHOOD_LOW)
LIKELIHOOD_LABELS = {LIKELIHOOD_HIGH: "haute", LIKELIHOOD_MEDIUM: "moyenne",
                     LIKELIHOOD_LOW: "basse"}
FAILURE_MODE_FIELDS = ("cause", "likelihood", "sensor", "no_sensor_reason")


HIGH_CAUSE_SENSOR_KINDS = (sensor_ref.KIND_LEVEL, sensor_ref.KIND_CATALYST)
PREMORTEM_FIELDS = ("bear_case", "change_mind", "failure_modes")
PREMORTEM_FIELD_LABELS = {"bear_case": "thèse adverse",
                          "change_mind": "ce qui me ferait changer d'avis",
                          "failure_modes": "pré-mortem"}






PREMORTEM_REQUIRED_FROM = datetime.date(2026, 10, 15)








VERDICT_HOLDS = "holds"
VERDICT_PARTLY_CHANGED = "partly_changed"
VERDICT_INVALIDATED = "invalidated"
VERDICTS = (VERDICT_HOLDS, VERDICT_PARTLY_CHANGED, VERDICT_INVALIDATED)
VERDICT_LABELS = {VERDICT_HOLDS: "tient", VERDICT_PARTLY_CHANGED: "en partie changée",
                  VERDICT_INVALIDATED: "invalidée"}











EVALUATE_ON_HELP = ("une date ISO AAAA-MM-JJ, ou catalyst:N (la N-ième échéance de "
                    "facts.catalysts)")







FORECAST_KEY_PREFIXES = ("forecast", "proba")

BARS = ("1D", "1W", "1M")
OPS = ("<", ">")

LEVEL_VALUE_KEYS = ("px", "trail", "sma")
TRAIL_RULES = ("higher-low",)


ACTIVE_CONTENT_FIELDS = ("thesis", "if_hit", "if_miss", "next_decision")

_ISO_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


class SchemaError(ValueError):
    """Une fiche refusee a l'ecriture. Le message nomme le champ et la valeur."""







_METHOD_HINTS = (
    (re.compile(r"fib", re.I), METHOD_FIB),
    (re.compile(r"faber|sma|moyenne mobile|filtre de tendance", re.I), METHOD_FABER),
    (re.compile(r"filet|\bnet\b", re.I), METHOD_NET),
    (re.compile(r"\brond|\bround\b", re.I), METHOD_ROUND),
    (re.compile(r"oblique|polarit|pivot", re.I), METHOD_PIVOT),
    (re.compile(r"m[èe]che|sommet|sommets|\bath\b|base|range|plancher|creux|"
                r"plus-bas|m[ée]moire|memory|mesur|support|r[ée]sistance",
                re.I), METHOD_MEMORY),
)





DEFAULT_METHOD = METHOD_MEMORY


def normalize_method(value: object) -> str | None:
    """Le jeton de méthode d'une valeur libre, ou None si rien ne l'identifie."""
    if not isinstance(value, str):
        return None
    text = value.strip()
    if text in METHODS:
        return text
    for pattern, method in _METHOD_HINTS:
        if pattern.search(text):
            return method
    return None


def normalize_horizon(value: object) -> str | None:
    """`long` ou `short`, ou None si la valeur ne tranche pas."""
    if not isinstance(value, str):
        return None
    text = value.strip()
    if text in HORIZONS:
        return text
    if re.match(r"^court\b|^tactique\b|^trade\b", text, re.I):
        return "short"
    if re.match(r"^long\b", text, re.I):
        return "long"
    return None


def normalize_status(value: object) -> str | None:
    """Le jeton de statut, français ou anglais, ou None si rien ne l'identifie."""
    if not isinstance(value, str):
        return None
    text = value.strip()
    if text in STATUSES:
        return text
    if re.match(r"^actif|^active", text, re.I):
        return STATUS_ACTIVE
    if re.match(r"^pr[ée]par|^draft", text, re.I):
        return STATUS_DRAFT
    if re.match(r"^[ée]cart|^dismiss", text, re.I):
        return STATUS_DISMISSED
    if re.match(r"^sold[ée]|^closed", text, re.I):
        return STATUS_CLOSED
    return None


def split_status(value: object) -> tuple[str | None, str | None]:
    """(jeton, nuance) — la nuance est ce que le jeton ne dit pas."""
    token = normalize_status(value)
    if token is None or not isinstance(value, str):
        return token, None
    text = value.strip()
    if text == token:
        return token, None
    parts = re.split(r"\s*[;:]\s*|\s+[—–]\s+", text, maxsplit=1)
    nuance = parts[1].strip() if len(parts) > 1 else None
    return token, nuance or None





def level_errors(level: object, where: str = "niveau") -> list[str]:
    """Les violations d'un niveau. Liste vide = conforme."""
    if not isinstance(level, dict):
        return [f"{where} : un niveau doit être un objet"]
    errors: list[str] = []
    for field in ("bar", "op", "method", "action"):
        if not level.get(field):
            errors.append(f"{where} : champ « {field} » manquant")
    if level.get("bar") and level["bar"] not in BARS:
        errors.append(f"{where} : bar « {level['bar']} » inconnu ({'|'.join(BARS)})")
    if level.get("op") and level["op"] not in OPS:
        errors.append(f"{where} : op « {level['op']} » inconnu (<|>)")
    if level.get("method") and level["method"] not in METHODS:
        errors.append(f"{where} : method « {level['method']} » hors doctrine "
                      f"({'|'.join(METHODS)})")

    sources = [key for key in LEVEL_VALUE_KEYS if key in level]
    if len(sources) != 1:
        errors.append(f"{where} : il faut EXACTEMENT un seuil px|trail|sma "
                      f"(trouvé : {sources or 'aucun'})")
    if "px" in level and not _number(level["px"]):
        errors.append(f"{where} : px non numérique ({level['px']!r})")
    if "trail" in level:
        trail = level["trail"]
        if not isinstance(trail, dict):
            errors.append(f"{where} : trail doit être un objet")
        else:
            if trail.get("rule") not in TRAIL_RULES:
                errors.append(f"{where} : trail.rule « {trail.get('rule')} » inconnu "
                              f"({'|'.join(TRAIL_RULES)})")
            if not _number(trail.get("seed")):
                errors.append(f"{where} : trail.seed doit être un nombre")
            confirm = trail.get("confirm", 2)


            if not isinstance(confirm, int) or isinstance(confirm, bool) or confirm < 1:
                errors.append(f"{where} : trail.confirm doit être un entier >= 1")
            errors += date_errors(trail.get("since"), "trail.since", where)
        if level.get("op") != "<":
            errors.append(f"{where} : trail n'a de sens qu'avec op « < » — "
                          "un palier qui monte est un PLANCHER, pas une cible")
    if "sma" in level:
        sma = level["sma"]
        window = sma.get("window") if isinstance(sma, dict) else None
        if not isinstance(window, int) or isinstance(window, bool) or window < 2:
            errors.append(f"{where} : sma.window doit être un entier >= 2 "
                          f"(trouvé {window!r})")
    arm = level.get("arm")
    if arm is not None:
        if (not isinstance(arm, dict) or arm.get("op") not in OPS
                or not _number(arm.get("px"))):
            errors.append(f"{where} : arm doit être {{op: <|>, px: nombre}}")
        elif not arm.get("since"):
            errors.append(f"{where} : arm sans « since » — un armement doit dater de "
                          "la naissance du suivi, sinon l'historique d'avant-plan "
                          "le déclenche (voir activated_on)")
        else:
            errors += date_errors(arm.get("since"), "arm.since", where)
    effect = level.get("effect")
    if effect is not None and effect not in EFFECTS:
        errors.append(f"{where} : effect « {effect} » inconnu ({'|'.join(EFFECTS)})")
    if "fraction" in level:
        fraction = level["fraction"]
        if effect != EFFECT_TRIM:
            errors.append(f"{where} : fraction n'a de sens qu'avec effect « trim »")
        elif not _number(fraction) or not 0 < fraction < 1:
            errors.append(f"{where} : fraction doit être un nombre entre 0 et 1 exclus "
                          f"(trouvé {fraction!r})")
    set_by = level.get("set_by")
    if set_by is not None and set_by not in SET_BY:
        errors.append(f"{where} : set_by « {set_by} » inconnu ({'|'.join(SET_BY)})")
    return errors


def _number(value: object) -> bool:
    """Un nombre du contrat — `True` n'en est pas un, même si `bool` hérite d'`int`."""
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def date_errors(value: object, field: str, where: str) -> list[str]:
    """Une date du contrat est ISO AAAA-MM-JJ, jamais une phrase."""
    if value in (None, ""):
        return []
    if not isinstance(value, str) or not _ISO_DATE.match(value):
        return [f"{where} : {field} doit être une date ISO AAAA-MM-JJ "
                f"(trouvé {value!r})"]


    try:
        datetime.date.fromisoformat(value)
    except ValueError:
        return [f"{where} : {field} n'est pas une date du calendrier (trouvé {value!r})"]
    return []


def evaluate_on_errors(value: object, where: str, *, facts: dict | None = None) -> list[str]:
    """La date de jugement de la thèse : une date ISO, ou `catalyst:N` qui existe."""
    if value in (None, ""):
        return []
    text = value.strip() if isinstance(value, str) else None
    if text and text.startswith(f"{sensor_ref.KIND_CATALYST}:"):
        return sensor_ref.ref_errors(text, f"{where} : evaluate_on", facts=facts)
    if text and _ISO_DATE.match(text):
        return date_errors(text, "evaluate_on", where)
    return [f"{where} : evaluate_on « {value} » hors contrat — {EVALUATE_ON_HELP}"]


def evaluate_on_write_errors(value: object, where: str, *, facts: dict | None = None) -> list[str]:
    """À l'ÉCRITURE seulement : l'échéance pointée doit porter une date ISO."""
    text = value.strip() if isinstance(value, str) else ""
    if facts is None or not text.startswith(f"{sensor_ref.KIND_CATALYST}:"):
        return []
    try:
        _kind, key = sensor_ref.parse(text)
    except ValueError:
        return []
    rows = facts.get("catalysts") if isinstance(facts.get("catalysts"), list) else []
    row = rows[int(key) - 1] if int(key) <= len(rows) else None
    if not isinstance(row, dict):
        return []
    day = str(row.get("date") or "")
    if _ISO_DATE.match(day) and not date_errors(day, "date", where):
        return []
    return [f"{where} : evaluate_on {text} — l'échéance pointée n'a pas de date ISO ({row.get('date')!r}) : "
            "le jugement en exige une ; écrire la date (AAAA-MM-JJ) ou pointer une échéance datée"]


def level_birth_needs_activated_on(level: object) -> bool:
    """Un `trail` ou un `arm` sans `since` prend sa naissance dans `activated_on`."""
    if not isinstance(level, dict):
        return False
    trail = level.get("trail")
    if isinstance(trail, dict) and not trail.get("since"):
        return True
    arm = level.get("arm")
    return bool(isinstance(arm, dict) and not arm.get("since"))





def _positive(value: object) -> bool:
    return _number(value) and value > 0


def threshold_errors(kind: object, threshold: object, where: str) -> list[str]:
    """Le seuil PROPRE à la ligne, selon le genre du critère."""
    if kind == CRITERION_CASH:
        if not isinstance(threshold, dict) or set(threshold) != {"min"} \
                or not _positive(threshold.get("min")):
            return [f"{where} : un critère « cash » exige threshold {{min: montant > 0}}"]
        return []
    if kind == CRITERION_DILUTION:
        if isinstance(threshold, dict) and set(threshold) == {"max_shares"} \
                and _positive(threshold.get("max_shares")):
            return []
        if isinstance(threshold, dict) and set(threshold) == {"max_pct", "base_shares"} \
                and _positive(threshold.get("max_pct")) and _positive(threshold.get("base_shares")):
            return []
        return [f"{where} : un critère « dilution » exige threshold {{max_shares: n}} "
                "ou {max_pct: p, base_shares: n}"]
    if threshold is not None and not (isinstance(threshold, str) and threshold.strip()):
        return [f"{where} : le seuil d'un critère « {kind} » est une phrase, "
                "la machine ne le mesure pas"]
    return []


def criteria_errors(criteria: object, where: str = "decision", *, decision: dict | None = None,
                    facts: dict | None = None, tripwire_ids: set[str] | None = None) -> list[str]:
    """Les violations de `decision.criteria`. Liste vide = conforme."""
    if criteria is None:
        return []
    if not isinstance(criteria, list):
        return [f"{where} : criteria doit être une liste"]
    errors: list[str] = []
    seen_ids: set[str] = set()
    seen_pillars: set[int] = set()
    for index, item in enumerate(criteria):
        at = f"{where} : criteria[{index}]"
        if not isinstance(item, dict):
            errors.append(f"{at} : un critère doit être un objet")
            continue
        ident = item.get("id")
        if not isinstance(ident, str) or not sensor_ref.TOKEN.match(ident):
            errors.append(f"{at} : id manquant ou illisible (minuscules ASCII, chiffres, tirets)")
        elif ident in seen_ids:
            errors.append(f"{at} : id « {ident} » en double")
        else:
            seen_ids.add(ident)
            at = f"{where} : critère {ident}"
        if not str(item.get("expect") or "").strip():
            errors.append(f"{at} : « expect » vide — ce qui doit être vrai, en une phrase")
        is_pillar = "pillar" in item
        allowed = PILLAR_FIELDS if is_pillar else CRITERION_FIELDS
        unknown = sorted(set(item) - set(allowed))
        if unknown:
            errors.append(f"{at} : champ(s) hors contrat {unknown} ({', '.join(allowed)})")
        errors += date_errors(item.get("by"), "by", at)
        if is_pillar:
            number = item.get("pillar")
            if not isinstance(number, int) or isinstance(number, bool) \
                    or not PILLAR_MIN <= number <= PILLAR_MAX:
                errors.append(f"{at} : pillar doit être un entier de {PILLAR_MIN} à {PILLAR_MAX}")
            elif number in seen_pillars:
                errors.append(f"{at} : pilier {number} en double")
            else:
                seen_pillars.add(number)
            if item.get("status") not in PILLAR_STATUSES:
                errors.append(f"{at} : status « {item.get('status')} » hors contrat "
                              f"({'|'.join(PILLAR_STATUSES)}) — un statut se DÉCLARE")
            if not item.get("sensor"):
                errors.append(f"{at} : un pilier exige son capteur lié (sensor)")
        else:
            if not item.get("by"):
                errors.append(f"{at} : un critère daté exige « by », sa date ISO")
            if item.get("kind") not in CRITERION_KINDS:
                errors.append(f"{at} : kind « {item.get('kind')} » hors contrat "
                              f"({'|'.join(CRITERION_KINDS)})")
            else:
                errors += threshold_errors(item["kind"], item.get("threshold"), at)
            if not str(item.get("if_missed") or "").strip():
                errors.append(f"{at} : « if_missed » vide — ce que la relecture devra trancher")
        if item.get("sensor") is not None:
            errors += sensor_ref.ref_errors(item["sensor"], f"{at} : sensor", decision=decision,
                                            facts=facts, tripwire_ids=tripwire_ids)

    return errors


def failure_modes_errors(items: object, where: str = "decision", *,
                         decision: dict | None = None, facts: dict | None = None,
                         tripwire_ids: set[str] | None = None) -> list[str]:
    """Les violations de `decision.failure_modes`. Liste vide = conforme."""
    if items is None:
        return []
    if not isinstance(items, list):
        return [f"{where} : failure_modes doit être une liste"]
    errors: list[str] = []
    for index, item in enumerate(items):
        at = f"{where} : failure_modes[{index}]"
        if not isinstance(item, dict):
            errors.append(f"{at} : une cause doit être un objet")
            continue
        unknown = sorted(set(item) - set(FAILURE_MODE_FIELDS))
        if unknown:
            errors.append(f"{at} : champ(s) hors contrat {unknown} ({', '.join(FAILURE_MODE_FIELDS)})")
        if not str(item.get("cause") or "").strip():
            errors.append(f"{at} : « cause » vide — pourquoi la ligne aurait échoué, en une phrase")
        likelihood = item.get("likelihood")
        if likelihood not in LIKELIHOODS:
            errors.append(f"{at} : likelihood « {likelihood} » hors contrat "
                          f"({'|'.join(LIKELIHOODS)}) — un ordre, jamais une probabilité")
        reason = item.get("no_sensor_reason")
        if reason is not None and not (isinstance(reason, str) and reason.strip()):
            errors.append(f"{at} : « no_sensor_reason » est une phrase")
        sensor = item.get("sensor")
        kind = None
        if sensor is not None:
            ref_problems = sensor_ref.ref_errors(sensor, f"{at} : sensor", decision=decision,
                                                 facts=facts, tripwire_ids=tripwire_ids)
            errors += ref_problems
            if not ref_problems:
                kind = sensor_ref.parse(sensor)[0]
        if kind in HIGH_CAUSE_SENSOR_KINDS and str(reason or "").strip():
            errors.append(f"{at} : « no_sensor_reason » contredit le capteur {sensor} déjà pointé")
        if likelihood == LIKELIHOOD_HIGH and kind not in HIGH_CAUSE_SENSOR_KINDS \
                and not str(reason or "").strip():
            errors.append(f"{at} : une cause « haute » pointe un niveau ou une échéance "
                          "(level:N, catalyst:N), ou dit pourquoi elle ne le peut pas "
                          "(no_sensor_reason)")
    return errors


def canonical_failure_mode(item: dict) -> dict:
    """Une cause dans l'ordre de lecture : la cause, sa vraisemblance, son capteur."""
    return {key: item[key] for key in FAILURE_MODE_FIELDS
            if key in item and not _drop_empty(item[key])}


def premortem_missing(decision: object) -> list[str]:
    """Les champs du pré-mortem absents ou vides, dans l'ordre de `PREMORTEM_FIELDS`."""
    if not isinstance(decision, dict):
        return list(PREMORTEM_FIELDS)
    return [field for field in PREMORTEM_FIELDS if _drop_empty(decision.get(field))
            or (isinstance(decision.get(field), str) and not decision[field].strip())]


def premortem_due(decision: object, *, held: bool | None, born_on: datetime.date | None,
                  today: datetime.date | None = None) -> bool:
    """Le pré-mortem est-il ATTENDU sur ce plan ? Jamais un refus : un badge."""
    if not isinstance(decision, dict) or decision.get("status") not in (STATUS_ACTIVE, STATUS_DRAFT):
        return False
    today = today or datetime.date.today()
    if held:
        try:
            start = datetime.date.fromisoformat(str(decision.get("activated_on")))
        except ValueError:
            return False
    else:
        start = born_on or today
    return start >= PREMORTEM_REQUIRED_FROM


def opens_plan(previous: object, decision: object) -> bool:
    """Cette écriture OUVRE-t-elle un plan ? (rien avant, ou un plan écarté ou soldé)."""
    if not isinstance(decision, dict) or decision.get("status") not in (STATUS_ACTIVE, STATUS_DRAFT):
        return False
    return not isinstance(previous, dict) or not previous \
        or previous.get("status") in (STATUS_DISMISSED, STATUS_CLOSED)


def canonical_criterion(item: dict) -> dict:
    """Un item dans l'ordre de lecture : identité, attendu, échéance, seuil, conséquence."""
    keys = PILLAR_FIELDS if "pillar" in item else CRITERION_FIELDS
    return {key: item[key] for key in keys if key in item and not _drop_empty(item[key])}





def decision_errors(decision: object, symbol: str = "", *, facts: dict | None = None,
                    tripwire_ids: set[str] | None = None) -> list[str]:
    """Les violations RÉPARABLES d'un bloc `decision`. Liste vide = conforme."""
    if decision is None or decision == {} or decision == []:
        return []
    if not isinstance(decision, dict):
        return [f"{symbol or 'decision'} : decision doit être un objet"]
    where = symbol or "decision"
    errors: list[str] = []

    status = decision.get("status")
    if isinstance(status, str) and status.strip() and status not in STATUSES:
        errors.append(f"{where} : status « {status} » hors contrat "
                      f"({'|'.join(STATUSES)})")
    status = status if isinstance(status, str) else ""

    horizon = decision.get("horizon")
    if isinstance(horizon, str) and horizon.strip() and horizon not in HORIZONS:
        errors.append(f"{where} : horizon « {horizon} » hors contrat "
                      f"({'|'.join(HORIZONS)})")

    role = decision.get("role")
    if isinstance(role, str) and role.strip() and role not in ROLES:
        errors.append(f"{where} : role « {role} » hors contrat "
                      f"({'|'.join(ROLES)})")

    errors += date_errors(decision.get("activated_on"), "activated_on", where)
    errors += date_errors(decision.get("review_by"), "review_by", where)
    errors += date_errors(decision.get("closed_on"), "closed_on", where)
    errors += evaluate_on_errors(decision.get("evaluate_on"), where, facts=facts)

    levels = decision.get("levels") or []
    if not isinstance(levels, list):
        errors.append(f"{where} : levels doit être une liste")
        levels = []
    for index, level in enumerate(levels):
        errors += level_errors(level, f"{where} : levels[{index}]")

    proxies = decision.get("proxy_levels")
    if proxies is not None and not isinstance(proxies, list):
        errors.append(f"{where} : proxy_levels doit être une liste")

    errors += criteria_errors(decision.get("criteria"), where, decision=decision,
                              facts=facts, tripwire_ids=tripwire_ids)
    for field in ("bear_case", "change_mind"):
        value = decision.get(field)
        if value is not None and not isinstance(value, str):
            errors.append(f"{where} : {field} est de la prose, une chaîne")
    errors += failure_modes_errors(decision.get("failure_modes"), where, decision=decision,
                                   facts=facts, tripwire_ids=tripwire_ids)
    for key in decision:
        if isinstance(key, str) and key.strip().lower().startswith(FORECAST_KEY_PREFIXES):
            errors.append(f"{where} : « {key} » n'appartient pas au bloc decision — une probabilité "
                          "s'écrit au registre des prévisions (scripts/forecasts.py)")

    if status == STATUS_ACTIVE:
        if decision.get("horizon") not in HORIZONS:
            errors.append(f"{where} : une décision active exige un horizon "
                          f"({'|'.join(HORIZONS)})")
        if (not levels and not proxies
                and not str(decision.get("no_levels_reason") or "").strip()):
            errors.append(f"{where} : une décision active sans aucun niveau exige "
                          "« no_levels_reason » — pourquoi aucun capteur n'est armé")
        if (any(level_birth_needs_activated_on(level) for level in levels)
                and not decision.get("activated_on")):
            errors.append(f"{where} : un trail ou un arm sans « since » exige "
                          "activated_on, sinon le niveau n'a pas de date de naissance")
    elif status == STATUS_DRAFT and not str(decision.get("thesis") or "").strip():
        errors.append(f"{where} : une préparation exige « thesis »")
    if status == STATUS_CLOSED and not decision.get("closed_on"):
        errors.append(f"{where} : une décision soldée exige « closed_on », "
                      "la date de la vente")
    elif status != STATUS_CLOSED and decision.get("closed_on"):
        errors.append(f"{where} : « closed_on » n'a de sens que sur une décision "
                      "soldée (status closed)")
    return errors


def decision_gaps(decision: object, symbol: str = "") -> list[str]:
    """Ce qui n'empêche pas de vivre mais se paie : le trou de CONTENU."""
    if not isinstance(decision, dict) or not decision:
        return []
    if decision.get("status") != STATUS_ACTIVE:
        return []
    where = symbol or "decision"
    return [f"{where} : « {field} » vide sur une décision active"
            for field in ACTIVE_CONTENT_FIELDS
            if not str(decision.get(field) or "").strip()]





ORDER = ("status", "notes", "thesis", "if_hit", "if_miss", "bear_case", "change_mind",
         "horizon",
         "role", "next_decision", "activated_on", "review_by", "evaluate_on", "closed_on",
         "no_levels_reason",
         "levels", "proxy_levels", "criteria", "failure_modes")


def _drop_empty(value: object) -> bool:
    return value is None or value == "" or value == [] or value == {}


def canonical_decision(decision: dict) -> dict:
    """Le bloc remis dans l'ordre canonique, sans clé vide ni inconnue."""
    out: dict = {}
    for key in ORDER:
        if key in decision and not _drop_empty(decision[key]):
            out[key] = decision[key]
    for key, value in decision.items():
        if key not in out and key not in ORDER and not _drop_empty(value):
            out[key] = value
    return out


def canonical_level(level: dict) -> dict:
    """Un niveau dans l'ordre de lecture : nom, barre, opérateur, seuil, méthode, action."""
    ordered: dict = {}
    for key in ("label", "bar", "op", "px", "trail", "sma", "arm", "method", "effect",
                "fraction", "action", "set_by"):
        if key in level and not _drop_empty(level[key]):
            ordered[key] = level[key]
    for key, value in level.items():
        if key not in ordered and not _drop_empty(value):
            ordered[key] = value
    return ordered








_EFFECT_NEGATIONS = re.compile(
    r"aucune?\s+(?:vente|achat|ordre|renfort|renforcement|entr[ée]e)\w*(?:\s+automatique)?"
    r"|pas\s+(?:de|d'|d’)\s*(?:vente|ordre|renfort|achat)[^;.,]*"
    r"|ni\s+(?:de\s+)?renfort|sans\s+vente[^;.,]*|sans\s+constituer[^;.]*"
    r"|ne\s+(?:d[ée]clenche|transmet|envoie)\w*\s+aucun\w*\s+\w+"
    r"|surveiller\s+la\s+sortie|la\s+sortie\s+reste|rel[èe]vement\s+de\s+la\s+sortie"
    r"|remonter\s+la\s+sortie|all[ée]ger\s+reste\s+libre|r[ée]trograd[ée]\s+d'all[ée]ger"
    r"|la\s+r[ée]duction\s+reste|signal\s+de\s+vente|sans\s+renforcer"
    r"|d[ée]clencheur\s+de\s+sortie\s+reste"
    r"|rel[eè]v\w*\s+(?:de\s+)?la\s+sortie|est\s+sortie"
    r"|sortie\s+(?:du|de\s+la|de)\s+(?:range|base|zone)",
    re.IGNORECASE)
_EFFECT_EXIT = re.compile(r"sorti|solder|vendre|\bsolde\b", re.IGNORECASE)
_EFFECT_TRIM = re.compile(r"r[ée]dui|r[ée]duction|all[ée]g|ramener\s+la\s+ligne", re.IGNORECASE)
_EFFECT_ADD = re.compile(r"renfor|l['’]entr[ée]e", re.IGNORECASE)
_EFFECT_WARN = re.compile(r"avertissement|relecture|relire|v[ée]rifier|surveiller|signale",
                          re.IGNORECASE)
_EFFECT_REVIEW = re.compile(
    r"revue|revoir|r[ée]examiner|invalid|refroidir|re-?d[ée]cider|re-?juger|contexte"
    r"|recalculer|trailing|d[ée]cision|confirm|reprise|relire|tenir|rel[eè]v",
    re.IGNORECASE)
_HALF = re.compile(r"moiti[ée]", re.IGNORECASE)


def infer_effect(level: dict) -> tuple[str | None, float | None]:
    """(effect, fraction) devinés de la prose d'un niveau, ou (None, None)."""
    if not isinstance(level, dict):
        return None, None


    text = _EFFECT_NEGATIONS.sub(" ", str(level.get("action") or level.get("label") or ""))
    op = level.get("op")
    exit_, trim = bool(_EFFECT_EXIT.search(text)), bool(_EFFECT_TRIM.search(text))
    add = bool(_EFFECT_ADD.search(text))
    if op == "<":
        if exit_ and trim:
            return None, None


        if exit_ or trim:
            gesture = (_EFFECT_EXIT if exit_ else _EFFECT_TRIM).search(text)
            review = re.search(r"revue|revoir", text, re.IGNORECASE)
            if review and review.start() < gesture.start():
                return None, None
        if exit_:
            return EFFECT_EXIT, None
        if trim:
            return EFFECT_TRIM, (0.5 if _HALF.search(text) else None)
        if add:
            return EFFECT_ADD, None
        if _EFFECT_WARN.search(text):
            return EFFECT_WARN, None
        if _EFFECT_REVIEW.search(text):
            return EFFECT_REVIEW, None
        return None, None
    if op == ">":
        if exit_ or trim:
            return None, None
        if add:
            return EFFECT_ADD, None
        if _EFFECT_REVIEW.search(text) or _EFFECT_WARN.search(text):
            return EFFECT_REVIEW, None
    return None, None


def level_effect(level: dict) -> str | None:
    """Le rôle écrit d'un niveau, sinon celui que sa prose dit sans ambiguïté."""
    if not isinstance(level, dict):
        return None
    if level.get("effect") in EFFECTS:
        return level["effect"]
    return infer_effect(level)[0]


def with_effect(level: dict) -> dict:
    """Le niveau avec son rôle : écrit, sinon déduit de sa prose quand elle est nette."""
    if level.get("effect") in EFFECTS:
        return level
    effect, fraction = infer_effect(level)
    if effect is None:
        return level
    out = dict(level, effect=effect)
    if fraction is not None:
        out["fraction"] = fraction
    return out


def validate_decision(decision: dict, symbol: str = "", *, facts: dict | None = None,
                      tripwire_ids: set[str] | None = None) -> dict:
    """Rend le bloc canonique, ou lève `SchemaError` avec TOUTES les violations."""
    errors = (decision_errors(decision, symbol, facts=facts, tripwire_ids=tripwire_ids)
              + decision_gaps(decision, symbol))
    if isinstance(decision, dict):
        errors += evaluate_on_write_errors(decision.get("evaluate_on"), symbol or "decision", facts=facts)
    if errors:
        raise SchemaError("\n".join(errors))
    cleaned = dict(decision)
    if isinstance(cleaned.get("levels"), list):
        cleaned["levels"] = [canonical_level(with_effect(level)) for level in cleaned["levels"]
                             if isinstance(level, dict)]
    if isinstance(cleaned.get("criteria"), list):
        cleaned["criteria"] = [canonical_criterion(item) for item in cleaned["criteria"]
                               if isinstance(item, dict)]
    if isinstance(cleaned.get("failure_modes"), list):
        cleaned["failure_modes"] = [canonical_failure_mode(item) for item in cleaned["failure_modes"]
                                    if isinstance(item, dict)]
    for field in ("bear_case", "change_mind", "evaluate_on"):
        if isinstance(cleaned.get(field), str):
            cleaned[field] = cleaned[field].strip()
    return canonical_decision(cleaned)




_COMPACT = re.compile(
    r"^\s*(?P<bar>1D|1W|1M)\s*(?P<op>[<>])\s*(?P<value>"
    r"(?:sma|trail)\s*\d+(?:\.\d+)?|\d+(?:\.\d+)?)"
    r"\s*(?:\((?P<method>[^)]*)\))?\s*(?:\[(?P<effect>[^\]]*)\])?\s*(?P<action>.+?)\s*$",
    re.IGNORECASE,
)

COMPACT_HELP = ("forme attendue : « 1W < 254.7 (mémoire) [sortie] sortie complète » ; "
                "« sma10 » et « trail19.2 » remplacent le nombre pour une règle "
                "calculée ; le rôle entre crochets (sortie, allègement, renfort, "
                "alerte, revue) est déduit de l'action s'il manque")












_HORIZON_INPUT = {"long": "long", "longterme": "long",
                  "short": "short", "court": "short", "courtterme": "short",
                  "tactique": "short", "trade": "short"}
_ROLE_INPUT = {ROLE_ENGINE: ROLE_ENGINE, ROLE_BALLAST: ROLE_BALLAST,
               "moteur": ROLE_ENGINE}
_EFFECT_INPUT = {**{effect: effect for effect in EFFECTS},
                 "sortie": EFFECT_EXIT, "allegement": EFFECT_TRIM, "alleger": EFFECT_TRIM,
                 "reduction": EFFECT_TRIM, "renfort": EFFECT_ADD, "entree": EFFECT_ADD,
                 "alerte": EFFECT_WARN, "avertissement": EFFECT_WARN, "revue": EFFECT_REVIEW}
_STATUS_INPUT = {"active": STATUS_ACTIVE, "actif": STATUS_ACTIVE,
                 "actifs": STATUS_ACTIVE, "suivi": STATUS_ACTIVE,
                 "actifsuivi": STATUS_ACTIVE,
                 "draft": STATUS_DRAFT, "preparee": STATUS_DRAFT,
                 "prepare": STATUS_DRAFT, "preparation": STATUS_DRAFT,
                 "prepareearelire": STATUS_DRAFT,
                 "dismissed": STATUS_DISMISSED, "ecarte": STATUS_DISMISSED,
                 "ecartee": STATUS_DISMISSED,
                 "closed": STATUS_CLOSED, "solde": STATUS_CLOSED,
                 "soldee": STATUS_CLOSED, "soldeepositionvendue": STATUS_CLOSED}


_PILLAR_INPUT = {**{status.replace("_", ""): status for status in PILLAR_STATUSES},
                 "enroute": PILLAR_ON_TRACK, "enretard": PILLAR_BEHIND,
                 "enattente": PILLAR_PENDING, "rompu": PILLAR_BROKEN, "casse": PILLAR_BROKEN}
_CRITERION_KIND_INPUT = {**{kind: kind for kind in CRITERION_KINDS},
                         "evenement": CRITERION_EVENT, "tresorerie": CRITERION_CASH,
                         "proprealaligne": CRITERION_CUSTOM, "propre": CRITERION_CUSTOM}


def coerce_criterion(item: object) -> object:
    """Un item saisi au clavier, jetons français acceptés, jetons anglais écrits."""
    if not isinstance(item, dict):
        return item
    out = dict(item)
    if isinstance(out.get("status"), str):
        out["status"] = _PILLAR_INPUT.get(_plain_key(out["status"]), out["status"])
    if isinstance(out.get("kind"), str):
        out["kind"] = _CRITERION_KIND_INPUT.get(_plain_key(out["kind"]), out["kind"])
    return out


_LIKELIHOOD_INPUT = {**{token: token for token in LIKELIHOODS},
                     "haute": LIKELIHOOD_HIGH, "haut": LIKELIHOOD_HIGH, "elevee": LIKELIHOOD_HIGH,
                     "forte": LIKELIHOOD_HIGH, "moyenne": LIKELIHOOD_MEDIUM,
                     "moyen": LIKELIHOOD_MEDIUM, "basse": LIKELIHOOD_LOW, "bas": LIKELIHOOD_LOW,
                     "faible": LIKELIHOOD_LOW}


def coerce_failure_mode(item: object) -> object:
    """Une cause saisie au clavier : « haute », « moyenne », « basse » écrivent le jeton anglais."""
    if not isinstance(item, dict):
        return item
    out = dict(item)
    if isinstance(out.get("likelihood"), str):
        out["likelihood"] = _LIKELIHOOD_INPUT.get(_plain_key(out["likelihood"]), out["likelihood"])
    return out


_VERDICT_INPUT = {**{token.replace("_", ""): token for token in VERDICTS},
                  "tient": VERDICT_HOLDS, "tenue": VERDICT_HOLDS,
                  "enpartiechangee": VERDICT_PARTLY_CHANGED, "partiellementchangee": VERDICT_PARTLY_CHANGED,
                  "changee": VERDICT_PARTLY_CHANGED, "partielle": VERDICT_PARTLY_CHANGED,
                  "invalidee": VERDICT_INVALIDATED, "invalide": VERDICT_INVALIDATED,
                  "cassee": VERDICT_INVALIDATED}


def coerce_verdict(value: str) -> str:
    """Le jeton de verdict d'une revue de thèse, saisi en français ou en anglais."""
    key = _plain_key(value)
    if key in _VERDICT_INPUT:
        return _VERDICT_INPUT[key]
    raise SchemaError(f"verdict inconnu : {value!r} ({'|'.join(VERDICTS)}, "
                      "ou tient|en partie changée|invalidée)")


def coerce_horizon(value: str) -> str:
    """Le jeton d'horizon d'une saisie CLI, française ou anglaise."""
    key = _plain_key(value)
    if key in _HORIZON_INPUT:
        return _HORIZON_INPUT[key]
    raise SchemaError(f"horizon inconnu : {value!r} "
                      "(long|short, ou long terme|court terme|tactique)")


def coerce_status(value: str) -> str:
    """Le jeton de statut d'une saisie CLI, française ou anglaise."""
    key = _plain_key(value)
    if key in _STATUS_INPUT:
        return _STATUS_INPUT[key]
    raise SchemaError(f"statut inconnu : {value!r} "
                      f"({'|'.join(STATUSES)}, ou leurs libellés français)")


def coerce_effect(value: str) -> str:
    """Le jeton de rôle d'un niveau, d'une saisie française ou anglaise."""
    key = _plain_key(value)
    if key in _EFFECT_INPUT:
        return _EFFECT_INPUT[key]
    raise SchemaError(f"rôle de niveau inconnu : {value!r} ({'|'.join(EFFECTS)}, "
                      "ou sortie|allègement|renfort|alerte|revue)")



_EVALUATE_NEXT_CATALYST = {"catalyst", "next", "echeance", "prochaineecheance", "catalyseur"}

_EVALUATE_NONE = {"none", "aucune", "aucun"}


def coerce_evaluate_on(value: str, facts: dict | None, today: datetime.date | None = None) -> str:
    """La date de jugement saisie au CLI : `catalyst` vise la prochaine échéance datée."""
    text = (value or "").strip()
    if not text or ":" in text:
        return text
    key = _plain_key(text)
    if key in _EVALUATE_NONE:
        return ""
    if key not in _EVALUATE_NEXT_CATALYST:
        return text
    today = today or datetime.date.today()
    rows = (facts or {}).get("catalysts") if isinstance((facts or {}).get("catalysts"), list) else []
    upcoming = []
    for index, row in enumerate(rows, start=1):
        day = str(row.get("date") or "") if isinstance(row, dict) else ""
        if _ISO_DATE.match(day) and not date_errors(day, "date", "") and day >= today.isoformat():
            upcoming.append((day, index))
    if upcoming:
        _day, index = min(upcoming)
        return f"{sensor_ref.KIND_CATALYST}:{index}"
    raise SchemaError(f"--evaluate-on {value} : aucune échéance datée à venir dans facts.catalysts "
                      f"— écrire la date ({EVALUATE_ON_HELP})")


def coerce_role(value: str) -> str:
    """Le jeton de rôle d'une saisie CLI, française ou anglaise."""
    key = _plain_key(value)
    if key in _ROLE_INPUT:
        return _ROLE_INPUT[key]
    raise SchemaError(f"rôle inconnu : {value!r} "
                      f"({'|'.join(ROLES)}, ou leurs libellés français)")


def _plain_key(text: str) -> str:
    import unicodedata

    folded = unicodedata.normalize("NFKD", text.strip().lower())
    return re.sub(r"[^a-z]", "", "".join(c for c in folded
                                         if not unicodedata.combining(c)))


def parse_level(text: str, label: str | None = None) -> dict:
    """`"1W < 254.7 (mémoire) sortie complète"` -> un niveau du contrat."""
    match = _COMPACT.match(text or "")
    if not match:
        raise SchemaError(f"niveau illisible : {text!r}\n{COMPACT_HELP}")
    value = match.group("value").strip()
    level: dict = {"bar": match.group("bar").upper(), "op": match.group("op")}
    lowered = value.lower()
    if lowered.startswith("sma"):
        window = value[3:].strip()
        if not window.isdigit():

            raise SchemaError(f"fenêtre de SMA non entière : {value!r}\n{COMPACT_HELP}")
        level["sma"] = {"window": int(window)}
    elif lowered.startswith("trail"):
        level["trail"] = {"rule": "higher-low", "seed": float(value[5:].strip())}
    else:
        level["px"] = float(value)
    method = (match.group("method") or "").strip()
    if method:


        level["method"] = method if method in METHODS \
            else (normalize_method(method) or method)
    if match.group("effect"):
        level["effect"] = coerce_effect(match.group("effect"))
    level["action"] = match.group("action").strip()
    if label:
        level["label"] = label
    return level
