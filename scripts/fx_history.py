#!/usr/bin/env python3
"""Archive hebdomadaire et mensuelle EUR/USD, pour exprimer les repères en dollars en euros."""
from __future__ import annotations

import argparse
import datetime
import json
import pathlib
import sys
import urllib.error

import atomic_file
import bar_calendar
import eodhd_history

SKILL = pathlib.Path(__file__).resolve().parent.parent
FX_DIR = SKILL / "data" / "fx"
ARCHIVE = FX_DIR / "EURUSD.json"
CODE = "EURUSD.FOREX"


PAIRS = {
    "EUR": "EURUSD", "GBP": "GBPUSD", "AUD": "AUDUSD",
    "JPY": "USDJPY", "CAD": "USDCAD", "CHF": "USDCHF", "HKD": "USDHKD",
    "INR": "USDINR", "PLN": "USDPLN", "KRW": "USDKRW", "TWD": "USDTWD",
}
DEPTH = "5y"

MIN_WEEKS = 52

MIN_MONTHS = 12


def _series(bars, today):
    stamps = [datetime.datetime.fromtimestamp(bar["t"] / 1000, datetime.timezone.utc)
              .date().isoformat() for bar in bars]
    return {
        "t": stamps,
        "c": [bar["c"] for bar in bars],
        "src": [bar["src"] for bar in bars],
        "fetched": today.isoformat(),
    }


def build(bars, *, key_kind, today=None, monthly=None, pair="EURUSD"):
    """Le document d'archive ; `monthly` (barres 1M) s'y ajoute quand il est tiré."""
    today = today or datetime.date.today()
    document = {
        "pair": pair,
        "unit": f"{pair[3:]} pour 1 {pair[:3]}",
        "source": eodhd_history.PROVIDER,
        "code": f"{pair}.FOREX",
        "key": key_kind,
        "fetched": today.isoformat(),
        "bars": {"1W": _series(bars, today)},
    }
    if monthly is not None:
        document["bars"]["1M"] = _series(monthly, today)
    return document


def _rates(path, bar, today):
    path = pathlib.Path(path)
    if not path.exists():
        return {}
    bars = (json.loads(path.read_text(encoding="utf-8")).get("bars") or {}).get(bar) or {}
    return {
        bar_calendar.period_end(stamp, bar).isoformat(): float(rate)
        for stamp, rate in bar_calendar.completed_series(bars, bar, as_of=today)
        if rate is not None and float(rate) > 0
    }


def weekly_rates(path=ARCHIVE, today=None):
    """{fin de semaine ISO : USD pour 1 EUR}, semaines réglées seulement ; {} sans archive."""
    return _rates(path, "1W", today)


def monthly_rates(path=ARCHIVE, today=None):
    """{dernier jour du mois ISO : USD pour 1 EUR}, mois réglés seulement ; {} sans barres 1M."""
    return _rates(path, "1M", today)


def archive_date(path=ARCHIVE):
    path = pathlib.Path(path)
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8")).get("fetched")


def last_settled_week_end(today=None):
    """Vendredi de la dernière semaine réglée (celle dont le vendredi est passé)."""
    today = today or datetime.date.today()
    friday = today - datetime.timedelta(days=(today.weekday() - 4) % 7)
    return friday if friday < today else friday - datetime.timedelta(days=7)


def last_settled_month_end(today=None):
    """Dernier jour du mois précédent : le dernier mois dont la fin est passée."""
    today = today or datetime.date.today()
    return today.replace(day=1) - datetime.timedelta(days=1)


def archive_path(pair):
    """Fichier d'archive d'une paire : `data/fx/<PAIRE>.json`."""
    return FX_DIR / f"{pair}.json"


class RatesUnavailable(LookupError):
    """Aucun taux réglé pour convertir une devise : le motif est dit, jamais tu."""


def usd_rates(currency, bar, *, as_of=None, fx_dir=None):
    """{clé de période `bar_period` : USD pour 1 unité de `currency`}, périodes réglées."""
    if currency == "USD":
        raise ValueError("le dollar n'a pas de taux contre lui-même")
    pair = PAIRS.get(currency)
    if not pair:
        raise RatesUnavailable(f"aucune paire de change connue pour la devise {currency}")
    path = (pathlib.Path(fx_dir) if fx_dir else FX_DIR) / f"{pair}.json"
    if not path.exists():
        raise RatesUnavailable(
            f"archive de change {pair} absente : python3 scripts/fx_history.py --currency {currency}")
    bars = (json.loads(path.read_text(encoding="utf-8")).get("bars") or {}).get(bar) or {}
    inverted = pair.startswith("USD")
    rates = {
        bar_calendar.bar_period(stamp, bar): (1 / float(rate) if inverted else float(rate))
        for stamp, rate in bar_calendar.completed_series(bars, bar, as_of=as_of)
        if rate is not None and float(rate) > 0
    }
    if not rates:
        raise RatesUnavailable(f"archive de change {pair} sans période {bar} réglée")
    return rates


def refresh_if_due(*, today=None, key=None, path=ARCHIVE, fetch=None, pair="EURUSD"):
    """Retire l'archive si sa dernière semaine réglée est en retard. Rend un motif."""
    today = today or datetime.date.today()
    label = f"{pair[:3]}/{pair[3:]}"
    rates = weekly_rates(path, today)
    months = monthly_rates(path, today)
    due = last_settled_week_end(today).isoformat()
    due_month = last_settled_month_end(today).isoformat()
    if rates and max(rates) >= due and months and max(months) >= due_month:
        return f"{label} à jour (semaine du {max(rates)}, fin de mois du {max(months)})"
    key = key or eodhd_history.api_key()
    if not key:
        return f"{label} en retard, clé EODHD absente"
    document, refusal = pull(key, "personal", today=today, path=path, fetch=fetch, pair=pair)
    if refusal:
        return f"{label} en retard, {refusal}"
    return f"{label} retiré jusqu'à la semaine du {max(weekly_rates(path, today))}"


def refresh_other_pairs_if_due(*, today=None, key=None, fetch=None, fx_dir=None):
    """Rafraîchit chaque archive de paire DÉJÀ amorcée hors EUR/USD ; un motif par paire."""
    fx_dir = pathlib.Path(fx_dir) if fx_dir else FX_DIR
    messages = []
    for pair in sorted(set(PAIRS.values()) - {"EURUSD"}):
        path = fx_dir / f"{pair}.json"
        if path.exists():
            messages.append(refresh_if_due(today=today, key=key, path=path, fetch=fetch, pair=pair))
    return " ; ".join(messages) or "aucune autre paire archivée"


def pull(key, key_kind, *, today=None, path=ARCHIVE, fetch=None, pair="EURUSD"):
    """Tirage, refus sous MIN_WEEKS, archive écrite : (document, None) ou (None, motif)."""
    fetch = fetch or eodhd_history.fetch_symbol
    code = f"{pair}.FOREX"
    try:
        bars = fetch(code, "1w", DEPTH, key=key, metadata={}, today=today)
        monthly = fetch(code, "1m", DEPTH, key=key, metadata={}, today=today)
    except (urllib.error.URLError, OSError) as exc:
        return None, f"EODHD injoignable : {exc}"
    except Exception as exc:



        return None, f"réponse EODHD inexploitable ({type(exc).__name__}: {exc})"
    if len(bars) < MIN_WEEKS:
        return None, f"{len(bars)} semaine(s) servie(s), moins de {MIN_WEEKS}"
    if len(monthly) < MIN_MONTHS:
        return None, f"{len(monthly)} mois servi(s), moins de {MIN_MONTHS}"
    document = build(bars, key_kind=key_kind, today=today, monthly=monthly, pair=pair)
    atomic_file.write_text(path, json.dumps(document, ensure_ascii=False) + "\n")
    return document, None


def main(argv=None):
    parser = argparse.ArgumentParser(description="Archives hebdomadaires et mensuelles de change (EODHD).")
    parser.add_argument("--demo", action="store_true", help="clé publique « demo » d'EODHD (EUR/USD seulement)")
    parser.add_argument("--show", action="store_true", help="affiche les dernières semaines archivées")
    parser.add_argument("--currency", action="append", choices=sorted(PAIRS),
                        help="devise à archiver contre le dollar (répétable ; défaut EUR)")
    parser.add_argument("--all", action="store_true", help="toutes les devises de PAIRS")
    args = parser.parse_args(argv)
    currencies = sorted(PAIRS) if args.all else (args.currency or ["EUR"])
    pairs = [PAIRS[currency] for currency in currencies]
    if args.show:
        status = 0
        for pair in pairs:
            path = archive_path(pair)
            rates = weekly_rates(path)
            if not rates:
                print(f"aucune archive : {path.relative_to(SKILL)}")
                status = 1
                continue
            print(f"{pair} : {len(rates)} semaine(s), tirée(s) le {archive_date(path)}")
            for week, rate in sorted(rates.items())[-5:]:
                print(f"  {week}  {rate:.5f}")
            months = monthly_rates(path)
            if not months:
                print("aucune fin de mois archivée : relancer le tirage")
            else:
                print(f"{len(months)} fin(s) de mois")
                for month, rate in sorted(months.items())[-3:]:
                    print(f"  {month}  {rate:.5f}")
        return status
    key = eodhd_history.DEMO_KEY if args.demo else eodhd_history.api_key()
    if not key:
        print(eodhd_history.available()[1] + " — --demo sert aussi EURUSD.FOREX")
        return 2
    status = 0
    for pair in pairs:
        path = archive_path(pair)
        document, refusal = pull(key, "demo" if args.demo else "personal", path=path, pair=pair)
        if refusal:
            print(f"{pair} : {refusal} — archive inchangée")
            status = 1
            continue
        last = document["bars"]["1W"]
        months = document["bars"]["1M"]
        print(f"{path.relative_to(SKILL)} : {len(last['t'])} semaines réglées, "
              f"{last['t'][0]} → {last['t'][-1]} (dernière {last['c'][-1]:.5f}) ; "
              f"{len(months['t'])} mois réglés, {months['t'][0]} → {months['t'][-1]}")
    return status


if __name__ == "__main__":
    sys.exit(main())
