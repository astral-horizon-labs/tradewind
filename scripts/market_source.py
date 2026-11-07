#!/usr/bin/env python3
"""Source principale de l'historique de prix d'une série : EODHD ou IBKR."""
from __future__ import annotations

import argparse
import collections
import json
import sys

import eodhd_guards
import market_identity







FALLBACK_SUFFIXES = {"US", "TO", "PA", "XETRA", "SW", "LSE", "AS", "BR", "OL",
                     "HK", "SHG", "SHE", "TW", "KO", "PR", "WAR", "INDX", "V"}





FALLBACK_EXCLUDED_CODES = {"VIX.INDX"}

PRIMARY_EODHD = "eodhd"
PRIMARY_IBKR = "ibkr"


_GUARDS = {}


def _verdicts(path=None):
    path = path or eodhd_guards.REGISTRY
    try:
        stat = path.stat()
    except OSError:
        return {}
    signature = (str(path), stat.st_mtime_ns, stat.st_size)
    if _GUARDS.get("signature") != signature:
        document = eodhd_guards.load(path) or {}
        _GUARDS.update(signature=signature, series={
            conid: entry.get("ok") for conid, entry in (document.get("series") or {}).items()})
    return _GUARDS["series"]


def _served_place(code):
    return code.rsplit(".", 1)[-1] in FALLBACK_SUFFIXES and code not in FALLBACK_EXCLUDED_CODES


def primary(conid, *, table=None, verdicts=None):
    """`eodhd` ou `ibkr` : la source qui prime pour l'historique de ce conid."""
    row = market_identity.symbol_for(conid, "eodhd", table=table)
    if not row or not _served_place(row["symbol"]):
        return PRIMARY_IBKR
    verdicts = _verdicts() if verdicts is None else verdicts
    return PRIMARY_EODHD if verdicts.get(str(conid)) is True else PRIMARY_IBKR


def main(argv=None):
    parser = argparse.ArgumentParser(description="Source principale de l'historique d'une série.")
    parser.add_argument("--conid", type=int, help="conid à interroger")
    parser.add_argument("--summary", action="store_true", help="décompte sur toute la table d'identité")
    args = parser.parse_args(argv)
    if args.conid:
        print(primary(args.conid))
        return 0
    if args.summary:
        table = market_identity.load()
        counts = collections.Counter(primary(conid, table=table) for conid in table)
        print(json.dumps(dict(counts), ensure_ascii=False))
        return 0
    parser.print_help()
    return 1


if __name__ == "__main__":
    sys.exit(main())
