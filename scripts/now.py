#!/usr/bin/env python3
"""Où en est-on dans le temps de marché ? — à exécuter au début de CHAQUE session."""

from __future__ import annotations

import datetime
from zoneinfo import ZoneInfo

NY = ZoneInfo("America/New_York")
PARIS = ZoneInfo("Europe/Paris")












US_OPEN = datetime.time(9, 30)
US_CLOSE = datetime.time(16, 0)

VENUES = [
    ("US (NYSE/NASDAQ…)", NY, US_OPEN, US_CLOSE, {0, 1, 2, 3, 4}, None, ""),
    ("Paris @SBF (Euronext)", PARIS, datetime.time(9, 0), datetime.time(17, 30), {0, 1, 2, 3, 4}, None, ""),
    ("Londres @LSE/@LSEETF", ZoneInfo("Europe/London"), datetime.time(8, 0), datetime.time(16, 30), {0, 1, 2, 3, 4}, None, ""),
    ("Canada @PURE (Cboe)", ZoneInfo("America/Toronto"), datetime.time(9, 30), datetime.time(16, 0), {0, 1, 2, 3, 4}, None, ""),
    ("Tel-Aviv @TASE", ZoneInfo("Asia/Jerusalem"), datetime.time(9, 59), datetime.time(17, 35), {0, 1, 2, 3, 4}, datetime.time(14, 0), " — lun-ven depuis 01/2026, ven écourté ~14h"),
]

FR_DAYS = ["lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche"]










US_HOLIDAYS = {









    "2025-01-01", "2025-01-09", "2025-01-20", "2025-02-17", "2025-04-18",
    "2025-05-26", "2025-06-19", "2025-07-04", "2025-09-01", "2025-11-27",
    "2025-12-25",
    "2026-01-01", "2026-01-19", "2026-02-16", "2026-04-03", "2026-05-25",
    "2026-06-19", "2026-07-03", "2026-09-07", "2026-11-26", "2026-12-25",








    "2027-01-01", "2027-01-18", "2027-02-15", "2027-03-26", "2027-05-31",
    "2027-06-18", "2027-07-05", "2027-09-06", "2027-11-25", "2027-12-24",
}
US_YEARS_COVERED = {2025, 2026, 2027}










US_EARLY_CLOSES = {"2025-07-03", "2025-11-28", "2025-12-24",
                   "2026-11-27", "2026-12-24", "2027-11-26"}
US_EARLY_CLOSE = datetime.time(13, 0)


def us_close_time(day: datetime.date) -> datetime.time:
    """Heure de clôture régulière de `day` à New York : 16 h, ou 13 h une demi-séance."""
    _is_us_holiday(day)
    return US_EARLY_CLOSE if day.isoformat() in US_EARLY_CLOSES else US_CLOSE


def _is_us_holiday(d: datetime.date) -> bool:
    if d.year not in US_YEARS_COVERED:
        raise SystemExit(
            f"US_HOLIDAYS ne couvre pas {d.year} — AJOUTER l'année dans now.py "
            f"(source : nyse.com, fermetures pleines) avant de faire confiance "
            f"au calendrier. Refus de deviner un férié.")
    return d.isoformat() in US_HOLIDAYS


def is_us_session(day: datetime.date) -> bool:
    """Vrai si `day` est une séance US complète ou écourtée, jamais un férié."""
    return day.weekday() < 5 and not _is_us_holiday(day)


def is_us_market_open(at: datetime.datetime | None = None) -> bool:
    """Vrai pendant la séance régulière US, en heure de New York."""
    ny = (at or datetime.datetime.now(NY)).astimezone(NY)
    return (is_us_session(ny.date())
            and US_OPEN <= ny.time() < us_close_time(ny.date()))


def next_us_market_open(at: datetime.datetime | None = None) -> datetime.datetime:
    """Prochaine ouverture régulière US, ou ouverture courante si elle arrive."""
    ny = (at or datetime.datetime.now(NY)).astimezone(NY)
    open_time = US_OPEN
    day = ny.date()
    if is_us_session(day) and ny.time() < open_time:
        return datetime.datetime.combine(day, open_time, tzinfo=NY)
    day += datetime.timedelta(days=1)
    while not is_us_session(day):
        day += datetime.timedelta(days=1)
    return datetime.datetime.combine(day, open_time, tzinfo=NY)




SESSION_STATE_LABELS = {
    "open": "séance US ouverte",
    "pre_open": "séance US à venir aujourd'hui",
    "closed": "séance US close",
}


def us_session_clock(at: datetime.datetime | None = None) -> dict:
    """L'horloge de la séance régulière US, dite en heure de PARIS."""
    ny = (at or datetime.datetime.now(NY)).astimezone(NY)
    today = ny.date()
    holiday_today = today.weekday() < 5 and _is_us_holiday(today)
    if is_us_session(today) and ny.time() < us_close_time(today):
        day = today
        state = "open" if ny.time() >= US_OPEN else "pre_open"
    else:
        day = next_us_market_open(ny).date()
        state = "closed"
    open_at = datetime.datetime.combine(day, US_OPEN, tzinfo=NY)
    close_at = datetime.datetime.combine(day, us_close_time(day), tzinfo=NY)
    open_paris, close_paris = open_at.astimezone(PARIS), close_at.astimezone(PARIS)
    offset = open_paris.utcoffset() - open_at.utcoffset()
    offset_hours = offset.total_seconds() / 3600
    return {
        "state": state,
        "state_label": SESSION_STATE_LABELS[state],
        "now_paris": ny.astimezone(PARIS).isoformat(timespec="seconds"),
        "now_new_york": ny.isoformat(timespec="seconds"),
        "session_day": day.isoformat(),
        "session_weekday": FR_DAYS[day.weekday()],
        "session_is_today": day == today,
        "open_paris": f"{open_paris:%H:%M}",
        "close_paris": f"{close_paris:%H:%M}",
        "open_new_york": f"{open_at:%H:%M}",
        "close_new_york": f"{close_at:%H:%M}",
        "open_at": open_at.isoformat(),
        "close_at": close_at.isoformat(),
        "changes_at": (close_at if state == "open" else open_at).isoformat(),
        "offset_hours": int(offset_hours) if offset_hours.is_integer() else offset_hours,
        "early_close": day.isoformat() in US_EARLY_CLOSES,
        "holiday_today": holiday_today,
    }


def _session(
    now: datetime.datetime,
    open_t: datetime.time,
    close_t: datetime.time,
    days: set[int],
    friday_close: datetime.time | None = None,
    holidays: frozenset | set = frozenset(),
) -> str:
    if now.date().isoformat() in holidays:
        return "FÉRIÉ — pas de séance"
    if now.weekday() not in days:
        return "pas de séance ce jour"
    if friday_close and now.weekday() == 4:
        close_t = friday_close
    t = now.time()
    if t < open_t:
        return f"À VENIR (ouvre à {open_t:%H:%M} locales)"
    if t < close_t:
        return f"EN COURS (clôture à {close_t:%H:%M} locales)"
    return "PASSÉE (clôturée)"


def _next_session(now: datetime.datetime, open_t: datetime.time, days: set[int],
                  holidays: frozenset | set = frozenset()) -> str:
    d = now.date()
    if now.weekday() in days and now.time() < open_t and d.isoformat() not in holidays:
        nxt = d
    else:
        nxt = d + datetime.timedelta(days=1)
        while nxt.weekday() not in days or nxt.isoformat() in holidays:
            nxt += datetime.timedelta(days=1)
    label = "aujourd'hui" if nxt == d else ("demain" if nxt == d + datetime.timedelta(days=1) else "")
    return f"{FR_DAYS[nxt.weekday()]} {nxt.isoformat()}" + (f" ({label})" if label else "")


def last_completed_us_session(now: datetime.datetime | None = None) -> datetime.date:
    """Date de la dernière séance US dont la clôture (16h NY) est passée."""
    ny = (now or datetime.datetime.now(NY)).astimezone(NY)
    d = ny.date()
    if ny.weekday() >= 5 or _is_us_holiday(d) or ny.time() < us_close_time(d):
        d -= datetime.timedelta(days=1)
    while not is_us_session(d):
        d -= datetime.timedelta(days=1)
    return d


def timestamp(now: datetime.datetime | None = None) -> str:
    """L'horodatage à COLLER dans un document — jamais tapé à la main."""
    now = now or datetime.datetime.now(PARIS)
    p_, n_ = now.astimezone(PARIS), now.astimezone(NY)
    return (f"{p_:%Y-%m-%d} à {p_:%Hh%M} Paris ({n_:%Hh%M} New York)")


def main() -> None:
    here = datetime.datetime.now(PARIS)
    ny = here.astimezone(NY)
    print(f"MAINTENANT   {FR_DAYS[here.weekday()]} {here.date().isoformat()}")
    print(f"             {here:%H:%M} à Paris — {ny:%H:%M} à New York")
    moment = "le matin" if here.hour < 12 else ("l'après-midi" if here.hour < 18 else "le soir")
    print(f"             (on est {moment} — ne pas écrire « ce soir » avant 18h Paris)")
    if here.year not in US_YEARS_COVERED:
        print(f"⚠⚠ US_HOLIDAYS ne couvre pas {here.year} — compléter now.py (nyse.com).")
    for name, tz, open_t, close_t, days, friday_close, note in VENUES:
        local = here.astimezone(tz)
        hol = US_HOLIDAYS if name.startswith("US") else frozenset()
        if name.startswith("US") and local.year in US_YEARS_COVERED:
            close_t = us_close_time(local.date())
        print(f"{name:<24} {_session(local, open_t, close_t, days, friday_close, hol)}{note}")
        print(f"{'':<24} prochaine : {_next_session(local, open_t, days, hol)}")
    if here.year in US_YEARS_COVERED:
        clock = us_session_clock(here)
        day = "aujourd'hui" if clock["session_is_today"] else f"{clock['session_weekday']} {clock['session_day']}"
        shift = "" if clock["offset_hours"] == 6 else f" — décalage de {clock['offset_hours']} h, changement d'heure"
        print(f"Séance US en heure de Paris ({day}) : {clock['open_paris']}–{clock['close_paris']}"
              f"{' (demi-séance)' if clock['early_close'] else ''}{shift}")
    print("Clôture hebdo : vendredi — " + (
        "C'EST AUJOURD'HUI" if here.weekday() == 4 else f"dans {(4 - here.weekday()) % 7} jour(s)"
    ))
    print("⚠ fériés et demi-séances US gérés (année couverte) ; fériés des autres places")
    print("  NON gérés : en cas de doute, calendrier de la place.")


if __name__ == "__main__":
    main()
