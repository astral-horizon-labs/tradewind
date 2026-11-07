#!/usr/bin/env python3
"""L'historique de NAV d'un livre sans Flex : les captures du connecteur, archivées."""
from __future__ import annotations

import argparse
import datetime
import json
import pathlib
import sys

import atomic_file
import data_root
import now as market_time


FLOW_NOISE = 1.0


class Refusal(ValueError):
    """Un refus actionnable : le message dit quoi faire."""


def archive_dir(data=None) -> pathlib.Path:
    """Le dossier de l'archive, sous le répertoire de données configuré."""
    return pathlib.Path(data or data_root.data_path()) / "connector" / "performance"


def _accounts(response: dict) -> dict:
    accounts = response.get("accounts")
    if not isinstance(accounts, dict) or not accounts:
        raise Refusal("capture sans bloc `accounts` : y coller la réponse brute de get_pa_performance_all_periods")
    return accounts


def _longest(account: dict) -> dict:
    """La période qui remonte le plus loin (le `1Y` en pratique)."""
    periods = account.get("periods") or {}
    usable = [p for p in periods.values() if isinstance(p, dict) and p.get("dates") and p.get("start_date")]
    if not usable:
        raise Refusal("capture sans période exploitable (dates, nav, cps)")
    return min(usable, key=lambda p: p["start_date"])


def archive(response: dict, *, at: datetime.datetime | None = None, data=None) -> pathlib.Path:
    """Archive la réponse brute, datée du jour de New York de la capture."""
    at = (at or datetime.datetime.now(market_time.NY)).astimezone(market_time.NY)
    for account in _accounts(response).values():
        period = _longest(account)
        if not (len(period["dates"]) == len(period.get("nav") or []) == len(period.get("cps") or [])):
            raise Refusal("capture incohérente : dates, nav et cps n'ont pas la même longueur")
    path = archive_dir(data) / f"pa-{at.date().isoformat()}.json"
    atomic_file.write_text(path, json.dumps({"captured_at": at.isoformat(timespec="seconds"),
                                             "response": response}, ensure_ascii=False, indent=1))
    return path


def _iso(compact: str) -> str:
    return f"{compact[:4]}-{compact[4:6]}-{compact[6:8]}"


def capture_points(capture: dict) -> dict[str, list[tuple[str, float, float]]]:
    """Compte → [(date ISO, NAV, cps)] des jours ouvrés clos à la capture, `start_nav` en tête."""
    at = datetime.datetime.fromisoformat(capture["captured_at"])
    closed = market_time.last_completed_us_session(at).isoformat()
    out = {}
    for name, account in _accounts(capture["response"]).items():
        period = _longest(account)
        points = []
        start_nav = period.get("start_nav")
        if isinstance(start_nav, (int, float)) and start_nav > 0:
            points.append((_iso(period["start_date"]), float(start_nav), 0.0))
        points += [(_iso(d), float(v), float(c))
                   for d, v, c in zip(period["dates"], period["nav"], period["cps"])]
        out[name] = [(d, v, c) for d, v, c in points
                     if d <= closed and datetime.date.fromisoformat(d).weekday() < 5 and v > 0]
    return out


def _captures(data=None) -> list[dict]:
    return [json.loads(path.read_text(encoding="utf-8"))
            for path in sorted(archive_dir(data).glob("pa-????-??-??.json"))]


def nav_and_flows(data=None) -> tuple[dict[str, float], dict[str, float]]:
    """(NAV par date, flux par date) de l'archive, comptes additionnés ; vide sans capture."""
    bases = {acc.get("base_currency") for c in _captures(data)
             for acc in _accounts(c["response"]).values()}
    if len(bases - {None}) > 1:
        raise Refusal(f"archive en plusieurs devises de base ({', '.join(sorted(bases - {None}))}) : "
                      "une NAV additionnée n'aurait pas de sens")
    per_account_nav: dict[tuple[str, str], float] = {}
    per_account_flow: dict[tuple[str, str], float] = {}
    for capture in _captures(data):
        for name, points in capture_points(capture).items():
            for i, (day, value, cps) in enumerate(points):
                per_account_nav[(day, name)] = value
                if i == 0:
                    continue
                _, prev_value, prev_cps = points[i - 1]
                r = (1 + cps) / (1 + prev_cps) - 1
                flow = value / (1 + r) - prev_value
                per_account_flow[(day, name)] = flow if abs(flow) >= FLOW_NOISE else 0.0
    nav: dict[str, float] = {}
    for (day, _name), value in sorted(per_account_nav.items()):
        nav[day] = nav.get(day, 0.0) + value
    flows: dict[str, float] = {}
    for (day, _name), flow in per_account_flow.items():
        if flow:
            flows[day] = flows.get(day, 0.0) + flow
    return nav, flows


def gaps(data=None) -> list[tuple[str, str]]:
    """Les intervalles entre deux séances consécutives de l'archive où des séances manquent."""
    nav, _ = nav_and_flows(data)
    days = sorted(nav)
    holes = []
    for prev, cur in zip(days, days[1:]):
        d = datetime.date.fromisoformat(prev) + datetime.timedelta(days=1)
        while d < datetime.date.fromisoformat(cur) and not market_time.is_us_session(d):
            d += datetime.timedelta(days=1)
        if d < datetime.date.fromisoformat(cur):
            holes.append((prev, cur))
    return holes


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Archive des performances du connecteur IBKR, historique de NAV.")
    parser.add_argument("capture", nargs="?", help="réponse brute de get_pa_performance_all_periods, ou « - »")
    parser.add_argument("--status", action="store_true", help="couverture de l'archive et ses trous")
    args = parser.parse_args(argv)
    try:
        if args.capture:
            try:
                raw = sys.stdin.read() if args.capture == "-" else pathlib.Path(args.capture).read_text(encoding="utf-8")
                response = json.loads(raw)
            except (OSError, json.JSONDecodeError) as exc:
                print(f"⛔ capture illisible : {exc}", file=sys.stderr)
                return 1
            print(f"capture archivée : {archive(response)}")
        nav, flows = nav_and_flows()
    except Refusal as exc:
        print(f"⛔ {exc}", file=sys.stderr)
        return 1
    if not nav:
        print(f"archive vide ({archive_dir()}) : y verser une capture de get_pa_performance_all_periods")
        return 1 if args.status else 0
    holes = gaps()
    print(f"NAV du {min(nav)} au {max(nav)} : {len(nav)} séance(s), {len(flows)} flux déduit(s), "
          f"{len(_captures())} capture(s)")
    for prev, cur in holes:
        print(f"  ⚠ trou entre {prev} et {cur} : aucune capture ne couvre ces séances")
    return 1 if holes and args.status else 0


if __name__ == "__main__":
    raise SystemExit(main())
