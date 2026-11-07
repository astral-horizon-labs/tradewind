#!/usr/bin/env python3
"""VEILLE DU REGISTRE CLINICALTRIALS.GOV — ce que le promoteur déclare avant de l'annoncer."""
from __future__ import annotations
import data_root

import argparse
import calendar
import datetime
import hashlib
import json
import pathlib
import re
import sys
import urllib.error
import urllib.parse
import urllib.request

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parent

import atomic_file

SHEETS = data_root.book_refs() / "instruments"


TRIALS_DIR = ROOT / "data" / "trials"

API = "https://clinicaltrials.gov/api/v2/studies"
STUDY_URL = "https://clinicaltrials.gov/study/{nct_id}"
USER_AGENT = "Astral Horizon Labs hello@astral-horizon-labs.com"
TIMEOUT_SECONDS = 30

CHUNK = 50
PAGE_SIZE = 100

MAX_PAGES = 20




STALE_DAYS = 3


FIELDS = (
    "protocolSection.identificationModule.nctId",
    "protocolSection.identificationModule.nctIdAliases",
    "protocolSection.identificationModule.briefTitle",
    "protocolSection.statusModule",
    "protocolSection.designModule.enrollmentInfo",
    "protocolSection.designModule.phases",
    "protocolSection.sponsorCollaboratorsModule.leadSponsor",
    "hasResults",
)

NCT_ID = re.compile(r"^NCT\d{8}$")
PROSE_NCT = re.compile(r"\bNCT\d{8}\b")

SPONSOR_DISCLAIMER = "Déclaratif du promoteur, à vérifier au 8-K."



CLINICAL_POCKET = "Thérapeutique clinique"

STOPPED_STATUSES = frozenset({"SUSPENDED", "TERMINATED", "WITHDRAWN"})

STATUS_LABELS = {
    "NOT_YET_RECRUITING": "pas encore en recrutement",
    "RECRUITING": "recrutement en cours",
    "ENROLLING_BY_INVITATION": "inclusion sur invitation",
    "ACTIVE_NOT_RECRUITING": "actif, recrutement clos",
    "COMPLETED": "terminé",
    "SUSPENDED": "suspendu",
    "TERMINATED": "arrêté",
    "WITHDRAWN": "retiré avant toute inclusion",
    "UNKNOWN": "statut inconnu (non vérifié depuis deux ans)",
    "WITHHELD": "statut retenu",
    "AVAILABLE": "accès élargi disponible",
    "NO_LONGER_AVAILABLE": "accès élargi fermé",
    "TEMPORARILY_NOT_AVAILABLE": "accès élargi suspendu",
    "APPROVED_FOR_MARKETING": "autorisé à la vente",
}
DATE_TYPE_LABELS = {"ESTIMATED": "estimée", "ACTUAL": "réelle"}
ENROLLMENT_TYPE_LABELS = {"ESTIMATED": "estimé", "ACTUAL": "réel"}


CHANGE_KINDS = ("stopped", "stop_reason", "status", "primary_completion_changed",
                "primary_completion_actual", "enrollment", "results_posted")
CHANGE_LABELS = {
    "stopped": "Essai suspendu, arrêté ou retiré",
    "stop_reason": "Motif d'arrêt modifié",
    "status": "Statut modifié",
    "primary_completion_changed": "Fin primaire modifiée",
    "primary_completion_actual": "Fin primaire devenue réelle",
    "enrollment": "Effectif modifié",
    "results_posted": "Résultats publiés au registre",
}

NOISE = "noise"
NOISE_FIELDS = ("last_update_posted", "status_verified", "completion", "title", "sponsor", "phases")
NOISE_LABELS = {
    "last_update_posted": "date de mise à jour",
    "status_verified": "vérification du statut",
    "completion": "fin d'étude",
    "title": "titre",
    "sponsor": "promoteur",
    "phases": "phases",
    "primary_completion_precision": "précision de la fin primaire",
    "results": "résultats",
}




CHECK_LABELS = {
    "unread": "registre pas encore relu",
    "not_found": "introuvable au registre",
    "stopped": "essai suspendu, arrêté ou retiré au registre",
    "results_posted": "résultats publiés au registre",
    "before_primary_completion": "échéance de la fiche antérieure à la fin primaire déclarée",
    "no_remark": "aucune remarque",
}

RUN_LABELS = {"ok": "à jour", "error": "en panne", "never": "jamais relu"}

SCOPE_HOLDING = "holding"
SCOPE_CANDIDATE = "candidate"
SCOPE_REFERENCE = "reference"

INBOX_SCOPES = (SCOPE_HOLDING, SCOPE_CANDIDATE)


class RegistryUnavailable(RuntimeError):
    """Le registre n'a pas répondu, ou pas lisiblement : AUCUN instantané n'est écrit."""




def paths(trials_dir: pathlib.Path | None = None) -> dict[str, pathlib.Path]:
    root = pathlib.Path(trials_dir or TRIALS_DIR)
    return {"root": root, "snapshots": root / "snapshots", "latest": root / "latest.json",
            "changes": root / "changes.jsonl", "run": root / "last-run.json"}


def _read_json(path: pathlib.Path) -> dict | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def _write_json(path: pathlib.Path, data: dict) -> None:
    atomic_file.write_text(path, json.dumps(data, ensure_ascii=False, indent=2) + "\n")


def _append(path: pathlib.Path, rows: list[dict]) -> None:
    """AJOUTE au journal ; une ligne écrite ne se réécrit jamais."""
    if not rows:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as stream:
        for row in rows:
            stream.write(json.dumps(row, ensure_ascii=False) + "\n")




def catalyst_nct_problems(sheet: object) -> list[str]:
    """Les défauts de `facts.catalysts[].nct_ids` d'une fiche (liste vide si saine)."""
    facts = sheet.get("facts") if isinstance(sheet, dict) else None
    rows = facts.get("catalysts") if isinstance(facts, dict) else None
    if not isinstance(rows, list):
        return []
    return [f"catalyseur {index} : {problem}"
            for index, row in enumerate(rows, start=1) for problem in row_nct_problems(row)]


def row_nct_problems(row: object) -> list[str]:
    """Les défauts de `nct_ids` sur UN catalyseur — relu aussi par §8 d'`update_check`."""
    if not isinstance(row, dict) or "nct_ids" not in row:
        return []
    ids = row["nct_ids"]
    if not isinstance(ids, list) or not ids:
        return ["nct_ids doit être une liste non vide (l'absence de la clé dit « aucun essai »)"]
    problems, seen = [], set()
    for value in ids:
        if not isinstance(value, str) or not NCT_ID.match(value):
            problems.append(f"identifiant {value!r} invalide (attendu NCT suivi de huit chiffres, en majuscules)")
        elif value in seen:
            problems.append(f"{value} en double")
        else:
            seen.add(value)
    return problems


def check_sheet(sheet: object) -> None:
    """Lève ValueError si `nct_ids` est mal formé — appelé par `jsonio.write`."""
    problems = catalyst_nct_problems(sheet)
    if problems:
        raise ValueError("nct_ids refusé : " + " ; ".join(problems))




def load_sheets(path: pathlib.Path | None = None) -> dict[str, dict]:
    """{symbole: fiche brute} — la prose compte, la projection plate ne suffit pas."""
    out: dict[str, dict] = {}
    for sheet_path in sorted(pathlib.Path(path or SHEETS).glob("*.json")):
        sheet = json.loads(sheet_path.read_text(encoding="utf-8"))
        if isinstance(sheet, dict):
            out[str(sheet.get("symbol") or sheet_path.stem).upper()] = sheet
    return out


def _catalyst_rows(sheet: dict) -> list:
    facts = sheet.get("facts") if isinstance(sheet.get("facts"), dict) else {}
    rows = facts.get("catalysts")
    return rows if isinstance(rows, list) else []


def sheet_links(sheets: dict[str, dict]) -> dict[str, list[dict]]:
    """{nct: [{symbol, source, catalyst_index}]} — `source` vaut `catalyst` ou `prose`."""
    links: dict[str, list[dict]] = {}
    for symbol, sheet in sorted(sheets.items()):
        structured: set[str] = set()
        for index, row in enumerate(_catalyst_rows(sheet)):
            ids = row.get("nct_ids") if isinstance(row, dict) else None
            for nct in ids if isinstance(ids, list) else []:
                if isinstance(nct, str) and NCT_ID.match(nct):
                    structured.add(nct)
                    links.setdefault(nct, []).append(
                        {"symbol": symbol, "source": "catalyst", "catalyst_index": index})
        prose = set(PROSE_NCT.findall(json.dumps(sheet, ensure_ascii=False))) - structured
        for nct in sorted(prose):
            links.setdefault(nct, []).append({"symbol": symbol, "source": "prose", "catalyst_index": None})
    return dict(sorted(links.items()))


def clinical_categories() -> frozenset[str]:
    """Les codes de catégorie rangés dans la poche « Thérapeutique clinique »."""
    import instrument_categories
    return frozenset(code for code, category in instrument_categories.CATEGORIES.items()
                     if category.pocket == CLINICAL_POCKET)




def query_url(nct_ids: list[str], page_token: str | None = None) -> str:
    """L'URL d'UNE requête groupée : des identifiants d'essai, rien d'autre."""
    params = {"filter.ids": ",".join(nct_ids), "fields": ",".join(FIELDS),
              "pageSize": str(PAGE_SIZE), "format": "json"}
    if page_token:
        params["pageToken"] = page_token
    return f"{API}?{urllib.parse.urlencode(params, safe=',.')}"


def _get_json(url: str, opener, timeout: float) -> dict:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
    try:
        with opener(request, timeout=timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        raise RegistryUnavailable(f"HTTP {error.code} sur l'API du registre") from error
    except (urllib.error.URLError, TimeoutError, OSError) as error:
        raise RegistryUnavailable(f"registre injoignable : {error}") from error
    except ValueError as error:
        raise RegistryUnavailable(f"réponse illisible du registre : {error}") from error
    if not isinstance(payload, dict):
        raise RegistryUnavailable("réponse inattendue du registre (pas un objet JSON)")
    return payload


def _dated(struct: object) -> dict | None:
    if not isinstance(struct, dict) or not struct.get("date"):
        return None
    return {"date": str(struct["date"]), "type": struct.get("type")}


def extract(study: dict) -> dict:
    """Les champs que la veille compare, tirés d'une étude de l'API v2."""
    protocol = study.get("protocolSection") or {}
    ident = protocol.get("identificationModule") or {}
    status = protocol.get("statusModule") or {}
    design = protocol.get("designModule") or {}
    sponsor = (protocol.get("sponsorCollaboratorsModule") or {}).get("leadSponsor") or {}
    enrollment = design.get("enrollmentInfo") or {}
    return {
        "nct_id": ident.get("nctId"),
        "aliases": list(ident.get("nctIdAliases") or []),
        "title": ident.get("briefTitle"),
        "sponsor": sponsor.get("name"),
        "phases": list(design.get("phases") or []),
        "overall_status": status.get("overallStatus"),
        "why_stopped": status.get("whyStopped"),
        "primary_completion": _dated(status.get("primaryCompletionDateStruct")),
        "completion": _dated(status.get("completionDateStruct")),
        "enrollment": ({"count": enrollment.get("count"), "type": enrollment.get("type")}
                       if enrollment.get("count") is not None else None),
        "has_results": bool(study.get("hasResults")),
        "results_first_posted": (status.get("resultsFirstPostDateStruct") or {}).get("date"),
        "last_update_posted": (status.get("lastUpdatePostDateStruct") or {}).get("date"),
        "status_verified": status.get("statusVerifiedDate"),
    }


def fetch(nct_ids, *, opener=None, timeout: float = TIMEOUT_SECONDS) -> tuple[dict[str, dict], list[str]]:
    """({nct demandé: étude}, introuvables) — requêtes groupées, pagination suivie."""
    opener = opener or urllib.request.urlopen
    wanted = sorted({str(value).strip().upper() for value in nct_ids if NCT_ID.match(str(value).strip().upper())})
    served: dict[str, dict] = {}
    for start in range(0, len(wanted), CHUNK):
        chunk = wanted[start:start + CHUNK]
        token = None
        for _ in range(MAX_PAGES):
            payload = _get_json(query_url(chunk, token), opener, timeout)
            for study in payload.get("studies") or []:
                row = extract(study) if isinstance(study, dict) else {}
                for key in [row.get("nct_id"), *row.get("aliases", [])]:
                    if key in chunk:
                        served[key] = row
            token = payload.get("nextPageToken")
            if not token:
                break
        else:
            raise RegistryUnavailable(f"pagination sans fin au-delà de {MAX_PAGES} pages")
    return served, [nct for nct in wanted if nct not in served]




def _day(text: object) -> datetime.date | None:
    """Une date du registre, précise au jour, au mois ou à l'année (premier jour)."""
    value = str(text or "")
    for pattern, fmt in ((r"^\d{4}-\d{2}-\d{2}$", "%Y-%m-%d"), (r"^\d{4}-\d{2}$", "%Y-%m"), (r"^\d{4}$", "%Y")):
        if re.match(pattern, value):
            return datetime.datetime.strptime(value, fmt).date()
    return None


def _period(text: object) -> tuple[str, datetime.date, datetime.date] | None:
    """(précision, premier jour, dernier jour) de la période qu'une date du registre désigne."""
    start = _day(text)
    if start is None:
        return None
    value = str(text)
    if len(value) == 10:
        return "day", start, start
    if len(value) == 7:
        last = calendar.monthrange(start.year, start.month)[1]
        return "month", start, start.replace(day=last)
    return "year", start, start.replace(month=12, day=31)


def _slip(before: object, after: object) -> int | None:
    """Le glissement en jours, mesuré à la précision la plus GROSSIÈRE des deux dates."""
    old, new = _period(before), _period(after)
    if not old or not new:
        return None
    if old[0] == new[0]:
        return (new[1] - old[1]).days
    if new[1] > old[2]:
        return (new[1] - old[2]).days
    if new[2] < old[1]:
        return (new[2] - old[1]).days
    return 0


def _slip_is_floor(before: object, after: object) -> bool:
    """Vrai si les deux dates n'ont pas la même précision : le glissement est un minimum."""
    old, new = _period(before), _period(after)
    return bool(old and new) and old[0] != new[0]


def _completion_dates(change: dict) -> tuple[object, object]:
    old, new = change.get("old"), change.get("new")
    return ((old or {}).get("date") if isinstance(old, dict) else None,
            (new or {}).get("date") if isinstance(new, dict) else None)


def _refines(before: str | None, after: str | None) -> bool:
    """Vrai si une date ne fait que se préciser (2029-02 → 2029-02-28), sans bouger."""
    return bool(before and after) and before != after and (after.startswith(before) or before.startswith(after))


def diff(old: dict, new: dict) -> list[dict]:
    """Les changements entre deux lectures d'un même essai, bruit compris."""
    changes: list[dict] = []

    def add(kind: str, field: str, before, after, **extra) -> None:
        changes.append({"kind": kind, "field": field, "material": kind != NOISE,
                        "old": before, "new": after, **extra})

    if old.get("overall_status") != new.get("overall_status"):
        kind = "stopped" if new.get("overall_status") in STOPPED_STATUSES else "status"
        add(kind, "overall_status", old.get("overall_status"), new.get("overall_status"),
            why_stopped=new.get("why_stopped"))
    elif old.get("why_stopped") != new.get("why_stopped"):
        add("stop_reason", "why_stopped", old.get("why_stopped"), new.get("why_stopped"))

    before, after = old.get("primary_completion"), new.get("primary_completion")
    if before != after:
        old_date, new_date = (before or {}).get("date"), (after or {}).get("date")
        old_type, new_type = (before or {}).get("type"), (after or {}).get("type")
        if old_type != "ACTUAL" and new_type == "ACTUAL":
            add("primary_completion_actual", "primary_completion", before, after,
                slip_days=_slip(old_date, new_date))
        elif old_date != new_date and _refines(old_date, new_date) and old_type == new_type:
            add(NOISE, "primary_completion_precision", before, after)
        else:
            add("primary_completion_changed", "primary_completion", before, after,
                slip_days=_slip(old_date, new_date))

    if old.get("enrollment") != new.get("enrollment"):
        add("enrollment", "enrollment", old.get("enrollment"), new.get("enrollment"))

    if ((not old.get("has_results") and new.get("has_results"))
            or (not old.get("results_first_posted") and new.get("results_first_posted"))):
        add("results_posted", "results", old.get("results_first_posted"), new.get("results_first_posted"))
    elif (old.get("has_results") != new.get("has_results")
          or old.get("results_first_posted") != new.get("results_first_posted")):
        add(NOISE, "results", old.get("results_first_posted"), new.get("results_first_posted"))

    for field in NOISE_FIELDS:
        if old.get(field) != new.get(field):
            add(NOISE, field, old.get(field), new.get(field))
    return changes


def _change_id(row: dict) -> str:
    """L'identité d'un changement : l'écart et la lecture d'où il part (`previous_on`)."""
    raw = json.dumps([row.get("previous_on"), row.get("nct_id"), row.get("kind"), row.get("field"),
                      row.get("old"), row.get("new")], ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:10]


def read_changes(trials_dir: pathlib.Path | None = None) -> list[dict]:
    """Le journal relu, une ligne illisible ignorée, un doublon écarté."""
    path = paths(trials_dir)["changes"]
    if not path.exists():
        return []
    rows, seen = [], set()
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            row = json.loads(line)
        except ValueError:
            continue
        if not isinstance(row, dict):
            continue
        ident = _change_id(row)
        if ident in seen:
            continue
        seen.add(ident)
        rows.append({**row, "id": ident})
    return rows




def _now_iso(now: datetime.datetime | None = None) -> str:
    return (now or datetime.datetime.now(datetime.UTC)).isoformat(timespec="seconds")


def read_run(trials_dir: pathlib.Path | None = None) -> dict | None:
    return _read_json(paths(trials_dir)["run"])


def collect(*, sheets: dict[str, dict] | None = None, trials_dir: pathlib.Path | None = None,
            today: datetime.date | None = None, now: datetime.datetime | None = None,
            opener=None) -> dict:
    """Relit le registre pour tous les NCT des fiches ; rend l'état de passe écrit."""
    where = paths(trials_dir)
    today = today or datetime.date.today()
    sheets = load_sheets() if sheets is None else sheets
    wanted = sorted(sheet_links(sheets))
    ran_at = _now_iso(now)
    previous = read_run(trials_dir) or {}
    where["root"].mkdir(parents=True, exist_ok=True)
    with atomic_file.locked(where["changes"]):
        if not wanted:
            run = {"status": "ok", "ran_at": ran_at, "last_success_at": ran_at, "requested": 0, "found": 0,
                   "not_found": [], "material": 0, "noise": 0, "snapshot": None,
                   "detail": "aucun NCT dans les fiches"}
            _write_json(where["run"], run)
            return run
        try:
            served, not_found = fetch(wanted, opener=opener)
        except RegistryUnavailable as error:
            run = {"status": "error", "ran_at": ran_at, "last_success_at": previous.get("last_success_at"),
                   "requested": len(wanted), "found": 0, "not_found": [], "material": 0, "noise": 0,
                   "snapshot": None, "detail": str(error)}
            _write_json(where["run"], run)
            return run
        snapshot = where["snapshots"] / f"{today.isoformat()}.json"
        _write_json(snapshot, {"version": 1, "collected_at": ran_at, "requested": wanted,
                               "not_found": not_found, "studies": served})
        latest = _read_json(where["latest"]) or {}
        known = latest.get("studies") if isinstance(latest.get("studies"), dict) else {}
        rows = []
        for nct, study in sorted(served.items()):
            before = known.get(nct)
            if isinstance(before, dict):
                for change in diff(before, study):
                    rows.append({"detected_on": today.isoformat(), "previous_on": before.get("seen_on"),
                                 "nct_id": nct, **change})
            known[nct] = {**study, "seen_on": today.isoformat()}
        _append(where["changes"], rows)
        _write_json(where["latest"], {"version": 1, "updated_on": today.isoformat(), "studies": known})
        run = {"status": "ok", "ran_at": ran_at, "last_success_at": ran_at, "requested": len(wanted),
               "found": len(served), "not_found": not_found,
               "material": sum(1 for row in rows if row["material"]),
               "noise": sum(1 for row in rows if not row["material"]),
               "snapshot": snapshot.name, "detail": None}
        _write_json(where["run"], run)
        return run




def status_label(token: object) -> str:
    return STATUS_LABELS.get(str(token), str(token or "statut non publié"))


def dated_label(value: object) -> str:
    """« 2029-02 (estimée) » ; « non publiée » si le registre ne la porte pas."""
    if not isinstance(value, dict) or not value.get("date"):
        return "non publiée"
    kind = DATE_TYPE_LABELS.get(str(value.get("type")))
    return f"{value['date']} ({kind})" if kind else str(value["date"])


def enrollment_label(value: object) -> str:
    if not isinstance(value, dict) or value.get("count") is None:
        return "non publié"
    kind = ENROLLMENT_TYPE_LABELS.get(str(value.get("type")))
    return f"{value['count']} ({kind})" if kind else str(value["count"])


def describe(change: dict) -> str:
    """Ancien et nouveau, en une phrase française, sans jugement."""
    kind, old, new = change.get("kind"), change.get("old"), change.get("new")
    if kind in ("stopped", "status"):
        text = f"statut {status_label(old)} → {status_label(new)}"
        if kind == "stopped":
            why = change.get("why_stopped")
            text += f", motif déclaré : « {why} »" if why else ", sans motif déclaré"
        return text
    if kind == "stop_reason":
        return f"motif d'arrêt « {old or '—'} » → « {new or '—'} »"
    if kind in ("primary_completion_changed", "primary_completion_actual"):
        text = f"fin primaire {dated_label(old)} → {dated_label(new)}"


        before, after = _completion_dates(change)
        slip = _slip(before, after)
        if slip:
            floor = "au moins " if _slip_is_floor(before, after) else ""
            verb = "glissée" if slip > 0 else "avancée"
            text += f", {verb} d'{floor}{abs(slip)} j" if floor else f", {verb} de {abs(slip)} j"
        return text
    if kind == "enrollment":
        return f"effectif {enrollment_label(old)} → {enrollment_label(new)}"
    if kind == "results_posted":
        return f"résultats publiés au registre le {new}" if new else "résultats publiés au registre"
    label = NOISE_LABELS.get(str(change.get("field")), str(change.get("field")))
    return f"{label} : {old if old is not None else '—'} → {new if new is not None else '—'}"


def _age_days(stamp: object, now: datetime.datetime) -> float | None:
    try:
        moment = datetime.datetime.fromisoformat(str(stamp))
    except ValueError:
        return None
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=datetime.UTC)
    return round((now - moment).total_seconds() / 86400, 1)


def run_state(trials_dir: pathlib.Path | None = None, *, now: datetime.datetime | None = None) -> dict:
    """La dernière passe, avec son âge et sa fraîcheur — `never` si aucune."""
    now = now or datetime.datetime.now(datetime.UTC)
    run = read_run(trials_dir)
    if not run:
        return {"status": "never", "ran_at": None, "last_success_at": None, "age_days": None, "stale": True,
                "requested": 0, "found": 0, "not_found": [], "material": 0, "noise": 0, "detail": None}
    age = _age_days(run.get("last_success_at"), now) if run.get("last_success_at") else None
    return {"status": run.get("status") if run.get("status") in ("ok", "error") else "error",
            "ran_at": run.get("ran_at"), "last_success_at": run.get("last_success_at"),
            "age_days": age, "stale": age is None or age > STALE_DAYS,
            "requested": int(run.get("requested") or 0), "found": int(run.get("found") or 0),
            "not_found": [str(nct) for nct in run.get("not_found") or []],
            "material": int(run.get("material") or 0), "noise": int(run.get("noise") or 0),
            "detail": run.get("detail")}


def _scope(symbol: str, held: set[str], candidates: set[str]) -> str:
    if symbol in held:
        return SCOPE_HOLDING
    return SCOPE_CANDIDATE if symbol in candidates else SCOPE_REFERENCE


def _if_miss(sheet: dict) -> str | None:
    decision = sheet.get("decision") if isinstance(sheet.get("decision"), dict) else {}
    text = decision.get("if_miss")
    return text.strip() if isinstance(text, str) and text.strip() else None


def _check(catalyst_date: object, study: dict | None, nct: str, run: dict) -> str:


    if nct in run["not_found"]:
        return "not_found"
    if study is None:
        return "unread"
    if study.get("overall_status") in STOPPED_STATUSES:
        return "stopped"
    if study.get("has_results"):
        return "results_posted"
    due = _day(catalyst_date)
    primary = _day((study.get("primary_completion") or {}).get("date"))
    if due and primary and due < primary:
        return "before_primary_completion"
    return "no_remark"


def registry_state(*, sheets: dict[str, dict] | None = None, trials_dir: pathlib.Path | None = None,
                   held: set[str] | None = None, candidates: set[str] | None = None,
                   now: datetime.datetime | None = None) -> dict:
    """Tout ce que la veille sait, SANS réseau : passe, essais, changements, recoupement, couverture."""
    sheets = load_sheets() if sheets is None else sheets
    held, candidates = set(held or ()), set(candidates or ())
    links = sheet_links(sheets)
    run = run_state(trials_dir, now=now)
    latest = (_read_json(paths(trials_dir)["latest"]) or {}).get("studies") or {}
    scoped = {nct: [{**link, "scope": _scope(link["symbol"], held, candidates)} for link in rows]
              for nct, rows in links.items()}

    studies = []
    for nct, rows in scoped.items():
        study = latest.get(nct) if isinstance(latest.get(nct), dict) else None
        missing = nct in run["not_found"]


        studies.append({"nct_id": nct, "url": STUDY_URL.format(nct_id=nct),
                        "found": study is not None and not missing,
                        "not_found": missing, "study": study, "links": rows})

    changes, noise_total = [], 0
    for row in read_changes(trials_dir):
        if not row.get("material"):
            noise_total += 1
            continue
        nct = str(row.get("nct_id"))
        extra = ({"slip_days": _slip(*_completion_dates(row))}
                 if row.get("field") == "primary_completion" else {})
        changes.append({**row, **extra, "url": STUDY_URL.format(nct_id=nct),
                        "kind_label": CHANGE_LABELS.get(str(row.get("kind")), str(row.get("kind"))),
                        "summary": describe(row), "links": scoped.get(nct, [])})
    changes.sort(key=lambda row: (row.get("detected_on") or "", row["id"]), reverse=True)

    checks = []
    for symbol, sheet in sorted(sheets.items()):
        for index, row in enumerate(_catalyst_rows(sheet)):
            ids = row.get("nct_ids") if isinstance(row, dict) else None
            for nct in ids if isinstance(ids, list) else []:
                if not isinstance(nct, str) or not NCT_ID.match(nct):
                    continue
                study = latest.get(nct) if isinstance(latest.get(nct), dict) else None
                verdict = _check(row.get("date"), study, nct, run)
                checks.append({"symbol": symbol, "catalyst_index": index, "catalyst_date": row.get("date"),
                               "nct_id": nct, "verdict": verdict, "label": CHECK_LABELS[verdict],
                               "registry_primary_completion": dated_label((study or {}).get("primary_completion"))
                               if study else None})

    clinical = clinical_categories()
    linked = {link["symbol"] for rows in links.values() for link in rows}
    followed = sorted(symbol for symbol, sheet in sheets.items()
                      if _scope(symbol, held, candidates) in INBOX_SCOPES
                      and ((sheet.get("identity") or {}).get("category") if isinstance(sheet.get("identity"), dict)
                           else None) in clinical)
    coverage = {
        "clinical_lines": len(followed),


        "followed": followed,
        "without_nct": [symbol for symbol in followed if symbol not in linked],
        "prose_only": [{"symbol": link["symbol"], "nct_id": nct, "scope": link["scope"]}
                       for nct, rows in scoped.items() for link in rows if link["source"] == "prose"],
    }


    malformed = [{"symbol": symbol, "problems": problems} for symbol, sheet in sorted(sheets.items())
                 if (problems := catalyst_nct_problems(sheet))]
    return {"run": run, "studies": studies, "changes": changes, "noise_total": noise_total,
            "checks": checks, "coverage": coverage, "malformed": malformed, "disclaimer": SPONSOR_DISCLAIMER}


def inbox_changes(state: dict, sheets: dict[str, dict]) -> list[dict]:
    """Les changements matériels qui deviennent une carte : un par ligne détenue ou candidate."""
    items = []
    for change in state["changes"]:
        for link in change["links"]:
            if link["scope"] not in INBOX_SCOPES:
                continue
            sheet = sheets.get(link["symbol"]) or {}
            verified_on = (sheet.get("state") or {}).get("verified_on") if isinstance(sheet.get("state"), dict) else None
            if isinstance(verified_on, str) and change.get("detected_on", "") < verified_on:
                continue
            if any(item["symbol"] == link["symbol"] and item["change"]["id"] == change["id"] for item in items):
                continue
            items.append({"symbol": link["symbol"], "scope": link["scope"], "change": change,
                          "if_miss": _if_miss(sheet)})
    return items


def registry_issues(state: dict) -> list[dict]:
    """Les négatifs mesurés de la veille, au format des données à corriger."""
    run, out = state["run"], []
    for row in state.get("malformed") or []:
        out.append({"id": f"trial-registry-nct:{row['symbol']}", "label": f"{row['symbol']} : nct_ids mal formé",
                    "status": "TRIAL_REGISTRY", "triggered_on": None, "date_label": "Constaté le",
                    "signal": f"{row['symbol']} : {' ; '.join(row['problems'])}. L’essai visé n’est pas relu "
                              "au registre ClinicalTrials.gov.",
                    "action": "Corriger facts.catalysts[].nct_ids dans la fiche (NCT suivi de huit chiffres, "
                              "lu sur clinicaltrials.gov)."})
    if not state["studies"]:
        return out
    if run["status"] == "never":
        out.append({"id": "trial-registry", "label": "Registre des essais jamais relu", "status": "TRIAL_REGISTRY",
                    "triggered_on": None, "date_label": "Constaté le",
                    "signal": f"{len(state['studies'])} NCT cité(s) dans les fiches, aucune passe du registre "
                              "ClinicalTrials.gov : un glissement de date n’y serait pas vu.",
                    "action": "Lancer trial_registry.py collect (le batch quotidien le fera aussi)."})
    elif run["status"] == "error":
        out.append({"id": "trial-registry", "label": "Registre des essais en panne", "status": "TRIAL_REGISTRY",
                    "triggered_on": (run["ran_at"] or "")[:10] or None, "date_label": "Passe du",
                    "signal": f"La dernière passe du registre a échoué : {run['detail']}. Aucun instantané "
                              "n’a été écrit.",
                    "action": "Relancer trial_registry.py collect."})
    elif run["stale"]:
        out.append({"id": "trial-registry", "label": "Registre des essais périmé", "status": "TRIAL_REGISTRY",
                    "triggered_on": (run["last_success_at"] or "")[:10] or None, "date_label": "Relu le",
                    "signal": f"Le registre a été relu il y a {run['age_days']} j (plus de {STALE_DAYS} j) : "
                              "un changement survenu depuis n’entre pas dans « À décider ».",
                    "action": "Relancer trial_registry.py collect."})
    for nct in run["not_found"]:
        symbols = sorted({link["symbol"] for study in state["studies"] if study["nct_id"] == nct
                          for link in study["links"]})
        out.append({"id": f"trial-registry:{nct}", "label": f"{nct} introuvable", "status": "TRIAL_REGISTRY",
                    "triggered_on": (run["ran_at"] or "")[:10] or None, "date_label": "Passe du",
                    "signal": f"{nct}, cité par {', '.join(symbols) or 'aucune fiche'}, est absent du registre "
                              "ClinicalTrials.gov : identifiant faux ou étude retirée.",
                    "action": "Vérifier l’identifiant sur la fiche et sur clinicaltrials.gov."})
    return out


def followed_lines(locate=None) -> tuple[set[str], set[str], list[str]]:
    """(détenus, candidats, avertissements) — UNE définition pour la route, le briefing, todo et la CLI."""
    import book
    import instrument_store
    warnings: list[str] = []
    try:
        held = set(book.reconciled_holdings((locate or book.latest_session_snapshot)()))

    except (FileNotFoundError, OSError, ValueError, KeyError, SystemExit) as error:
        held = set()
        warnings.append(f"livre illisible, aucune ligne comptée détenue : {error}")
    try:
        candidates = set(instrument_store.watchlist_symbols())
    except (OSError, ValueError) as error:
        candidates = set()
        warnings.append(f"liste de candidats illisible : {error}")
    return held, candidates, warnings



BRIEF_DAYS = 7


def brief_summary() -> str:
    """Une ligne pour le briefing : les négatifs, PUIS les changements matériels récents, la couverture."""
    try:
        held, candidates, warnings = followed_lines()
        sheets = load_sheets()
        state = registry_state(sheets=sheets, held=held, candidates=candidates)
    except Exception as error:
        return f"⚠ REGISTRE DES ESSAIS indisponible : {error}"
    if not state["studies"] and not state["malformed"]:
        return "registre des essais — aucune fiche ne cite de NCT : rien à relire."
    negatives = [*warnings, *(issue["signal"] for issue in registry_issues(state))]
    parts = [text.rstrip(".") for text in negatives[:2]]
    if len(negatives) > 2:
        parts.append(f"et {len(negatives) - 2} autre(s) négatif(s) — trial_registry.py status")
    since = (datetime.date.today() - datetime.timedelta(days=BRIEF_DAYS)).isoformat()
    recent = [item for item in inbox_changes(state, sheets) if item["change"]["detected_on"] >= since]
    if recent:
        head = ", ".join(f"{item['symbol']} {item['change']['nct_id']} {item['change']['kind_label'].lower()}"
                         for item in recent[:4])
        parts.append(f"{len(recent)} changement(s) matériel(s) sur une ligne suivie depuis {BRIEF_DAYS} j : "
                     f"{head}{'…' if len(recent) > 4 else ''}")
    coverage = state["coverage"]
    tail = (f"{len(coverage['without_nct'])} ligne(s) clinique(s) suivie(s) sans NCT, "
            f"{len(coverage['prose_only'])} NCT en prose seulement")
    if parts:
        return ("⚠ REGISTRE DES ESSAIS — " + " ; ".join([*parts, tail]) + "."
                + (f" {SPONSOR_DISCLAIMER}" if recent else ""))
    run = state["run"]
    return (f"registre des essais — {run['found']} NCT relu(s) le {(run['last_success_at'] or '')[:10]}, "
            f"aucun changement matériel sur une ligne suivie depuis {BRIEF_DAYS} j "
            f"(bruit de la passe : {run['noise']}) ; {tail}.")




def _print_status(state: dict) -> None:
    run = state["run"]
    print(f"REGISTRE DES ESSAIS — passe {RUN_LABELS[run['status']]}"
          + (f", dernière réussite {run['last_success_at']}" if run["last_success_at"] else ""))
    if run["detail"]:
        print(f"  {run['detail']}")
    print(f"  {len(state['studies'])} NCT cité(s) dans les fiches ; bruit au journal : {state['noise_total']}")
    for issue in registry_issues(state):
        print(f"  ⚠ {issue['label']} — {issue['signal']}")
    for study in state["studies"]:
        row = study["study"] or {}
        symbols = ", ".join(f"{link['symbol']}{'' if link['source'] == 'catalyst' else ' (prose)'}"
                            for link in study["links"])
        if not study["found"]:
            print(f"  {study['nct_id']}  {symbols} — {'introuvable' if study['not_found'] else 'pas encore relu'}")
            continue
        print(f"  {study['nct_id']}  {symbols} — {status_label(row.get('overall_status'))}, "
              f"fin primaire {dated_label(row.get('primary_completion'))}, "
              f"effectif {enrollment_label(row.get('enrollment'))}, relu le {row.get('seen_on')}")


def _print_changes(state: dict, symbol: str | None, everything: bool, trials_dir=None) -> None:
    rows = state["changes"]
    if everything:
        rows = sorted(read_changes(trials_dir), key=lambda row: row.get("detected_on") or "", reverse=True)
        rows = [{**row, "kind_label": CHANGE_LABELS.get(str(row.get("kind")), "bruit"),
                 "summary": describe(row)} for row in rows]
        linked = sheet_links(load_sheets())
        rows = [{**row, "links": linked.get(str(row.get("nct_id")), [])} for row in rows]
    if symbol:
        rows = [row for row in rows if any(link["symbol"] == symbol for link in row.get("links") or [])]
    if not rows:
        print("aucun changement au journal" + (f" pour {symbol}" if symbol else "") + ".")
        return
    for row in rows:
        symbols = ", ".join(sorted({link["symbol"] for link in row.get("links") or []})) or "—"
        print(f"  {row.get('detected_on')}  {row.get('nct_id')}  {symbols:12}  {row['kind_label']} — {row['summary']}")
    print(f"  {SPONSOR_DISCLAIMER}")


def _print_coverage(state: dict) -> None:
    coverage = state["coverage"]
    print(f"LIGNES CLINIQUES SUIVIES (détenues ou candidates) : {coverage['clinical_lines']}")
    print(f"  sans aucun NCT ({len(coverage['without_nct'])}) : {', '.join(coverage['without_nct']) or 'aucune'}")
    print(f"  NCT cités en prose seulement ({len(coverage['prose_only'])}) — à rattacher à un catalyseur "
          "par facts.catalysts[].nct_ids :")
    for row in coverage["prose_only"]:
        print(f"    · {row['symbol']:6} {row['nct_id']}")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Veille du registre ClinicalTrials.gov sur les NCT des fiches.")
    sub = ap.add_subparsers(dest="command", required=True)
    run = sub.add_parser("collect", help="passe réseau : relit le registre et écrit l'instantané du jour")
    run.add_argument("--quiet", action="store_true", help="une ligne de bilan (batch quotidien)")
    for name, text in (("status", "dernière passe, essais et négatifs, sans réseau"),
                       ("changes", "les changements au journal, sans réseau"),
                       ("coverage", "lignes cliniques sans NCT et NCT en prose seulement")):
        parser = sub.add_parser(name, help=text)
        parser.add_argument("--json", action="store_true", help="sortie JSON")
        if name == "changes":
            parser.add_argument("--symbol", help="une seule ligne")
            parser.add_argument("--all", action="store_true", help="le bruit compté aussi")
    args = ap.parse_args(argv)

    if args.command == "collect":
        result = collect()
        line = (f"registre des essais — {result['found']}/{result['requested']} NCT relus, "
                f"{result['material']} changement(s) matériel(s), {result['noise']} de bruit"
                + (f", introuvables : {', '.join(result['not_found'])}" if result["not_found"] else "")
                if result["status"] == "ok" else
                f"registre des essais indisponible — {result['detail']} (aucun instantané écrit)")
        print(line)
        if not args.quiet and result["status"] == "ok":
            print(f"  instantané : {result['snapshot']}")
        return 0 if result["status"] == "ok" else 1

    held, candidates, warnings = followed_lines()
    state = registry_state(held=held, candidates=candidates)
    if getattr(args, "json", False):
        print(json.dumps({**state, "warnings": warnings}, ensure_ascii=False, indent=2))
        return 0
    for warning in warnings:
        print(f"⚠ {warning}")
    if args.command == "status":
        _print_status(state)
    elif args.command == "changes":
        _print_changes(state, (args.symbol or "").upper() or None, args.all)
    else:
        _print_coverage(state)
    return 0


if __name__ == "__main__":
    sys.exit(main())
