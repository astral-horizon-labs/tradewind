#!/usr/bin/env python3
"""Table d'identité multi-sources : conid -> symboles IBKR, EODHD et TradingView, datés."""
from __future__ import annotations
import data_root

import argparse
import datetime
import json
import pathlib
import re
import sys

import jsonio

HERE = pathlib.Path(__file__).resolve().parent
SKILL = HERE.parent
REFS = SKILL / "references"
CACHE = data_root.prices_dir()
IDENTITY = REFS / "market-identity.json"
RATIO_MANIFEST = data_root.universe_file()
BASKETS = REFS / "baskets.json"
SHEETS = data_root.book_refs() / "instruments"
TRANSITIONS = REFS / "basket-contracts.json"

PROVIDERS = ("ibkr", "eodhd", "tradingview")









CURRENCY_BY_IBKR_EXCHANGE = {
    "NASDAQ": "USD", "NYSE": "USD", "ARCA": "USD", "BATS": "USD", "AMEX": "USD",
    "PINK": "USD", "COINBASE": "USD",
    "TSE": "CAD", "TSX": "CAD", "VENTURE": "CAD", "PURE": "CAD",
    "SBF": "EUR", "IBIS": "EUR", "FWB2": "EUR", "GETTEX": "EUR", "AEB": "EUR",
    "ENEXT.BE": "EUR", "BVME": "EUR", "BVME.ETF": "EUR",
    "LSE": "GBP", "ASX": "AUD", "TSEJ": "JPY", "SEHK": "HKD", "EBS": "CHF",
    "NSE": "INR", "WSE": "PLN", "KRX": "KRW", "TWSE": "TWD",
}


def exchange_currency(exchange) -> str:
    """Devise de la place IBKR `exchange`, ou « ? » si la place est inconnue."""
    return CURRENCY_BY_IBKR_EXCHANGE.get(exchange, "?")


def record_currency(meta) -> str:
    """Devise d'une ligne du manifeste : son champ `currency`, sinon sa place."""
    return meta.get("currency") or exchange_currency(meta.get("exchange"))






EODHD_SUFFIX_BY_IBKR_EXCHANGE = {
    "NASDAQ": "US", "NYSE": "US", "AMEX": "US", "ARCA": "US", "BATS": "US",
    "PINK": "US",
    "TSE": "TO", "TSX": "TO",



    "VENTURE": "V",
    "IBIS": "XETRA", "IBIS2": "XETRA",
    "SFB": "ST",
    "SBF": "PA", "AEB": "AS", "ENEXT.BE": "BR",
    "OSE": "OL",
    "EBS": "SW",
    "LSE": "LSE", "LSEETF": "LSE",
    "SEHK": "HK",
    "SEHKNTL": "SHG", "SEHKSTAR": "SHG",
    "SEHKSZSE": "SHE", "CHINEXT": "SHE",
    "TWSE": "TW",
    "KRX": "KO",
    "PRA": "PR",


    "WSE": "WAR",
}




EODHD_SUFFIX_BY_TV_PREFIX = {
    "NASDAQ": "US", "NYSE": "US", "AMEX": "US", "OTC": "US",
    "TSX": "TO", "XETR": "XETRA", "OMXSTO": "ST", "OSL": "OL",
    "EURONEXT": None, "SIX": "SW", "LSE": "LSE",
    "HKEX": "HK", "SSE": "SHG", "SZSE": "SHE", "TWSE": "TW", "KRX": "KO",
    "PSECZ": "PR", "GPW": "WAR", "TSXV": "V",
}


UNCONFIRMED_PLACES = {
    "BVME": "Milan : non couvert par EODHD (404)",
    "BVME.ETF": "Milan : non couvert par EODHD (404)",
    "TSEJ": "Tokyo : non couvert par EODHD (404)",
    "NSE": "Inde : non couvert par EODHD (404)",
    "ASX": "ASX : clôtures EODHD et IBKR divergentes (≤ 25 séances sur 102 égales)",
    "PURE": "PURE : place IBKR sans équivalent EODHD sûr (WUC à 1,7 %)",
    "FWB": "Francfort : place IBKR différente de celle d'EODHD",
    "FWB2": "Francfort : place IBKR différente de celle d'EODHD",
    "GETTEX": "gettex : non servi par EODHD (Francfort à 0,13 %)",
    "TASE": "Tel-Aviv : non mesuré",
}



DECLARED_RENAMES = {
    "38251658": {
        "proof": "8-K 0001193125-26-378529 (fusion Helix–Hornbeck), commit 1add7d35",
        "ibkr": [{"symbol": "HLX", "to": "2026-09-01"},
                 {"symbol": "HOS", "from": "2026-09-02"}],
        "tradingview": [{"symbol": "NYSE:HLX", "to": "2026-09-01"},
                        {"symbol": "NYSE:HOS", "from": "2026-09-02"}],
    },






    "759914780": {
        "proof": ("Chapter 11 (Delaware, 28/08/2026), suspension Nasdaq au 08/09/2026 ; "
                  "BTAIQ.US = BTAI.US jusqu'au 08/10/2026 puis = séances IBKR"),
        "ibkr": [{"symbol": "BTAI", "to": "2026-09-07"},
                 {"symbol": "BTAIQ", "from": "2026-09-08"}],
        "tradingview": [],
        "eodhd": [{"symbol": "BTAIQ.US"}],
    },





    "939700796": {
        "proof": "changement de nom Adial → Azora Therapeutics, AZR au Nasdaq le 29/10/2026 (GlobeNewswire 28/10/2026)",
        "ibkr": [{"symbol": "ADIL", "to": "2026-10-28"},
                 {"symbol": "AZR", "from": "2026-10-29"}],
        "tradingview": [{"symbol": "NASDAQ:ADIL", "to": "2026-10-28"},
                        {"symbol": "NASDAQ:AZR", "from": "2026-10-29"}],
        "eodhd": [{"symbol": "AZR.US"}],
    },
}






PROVEN_CANDIDATES: dict[str, str] = {
    "361102890": "BWAY — 2026-10-02, 26 périodes réglées, écart max 0.00%",
    "211651700": "COPX — 2026-10-02, 26 périodes réglées, écart max 0.00%",
    "259025784": "COWZ — 2026-10-02, 52 périodes réglées, écart max 0.00%",
    "97462781": "CPER — 2026-10-02, 26 périodes réglées, écart max 0.00%",
    "229725583": "CRAK — 2026-10-02, 26 périodes réglées, écart max 0.01%",
    "741192239": "ETH — 2026-10-02, 52 périodes réglées, écart max 0.00%",
    "677037673": "IBIT — 2026-10-02, 26 périodes réglées, écart max 0.00%",
    "12658199": "IGV — 2026-10-02, 26 périodes réglées, écart max 0.00%",
    "39046985": "IHI — 2026-10-02, 26 périodes réglées, écart max 0.00%",
    "229727413": "ISRA — 2026-10-02, 52 périodes réglées, écart max 0.02%",
    "192643858": "JETS — 2026-10-02, 52 périodes réglées, écart max 0.00%",
    "45540872": "KIE — 2026-10-02, 26 périodes réglées, écart max 0.00%",
    "581445011": "PDBA — 2026-10-02, 26 périodes réglées, écart max 0.02%",
    "253190571": "PICK — 2026-10-02, 52 périodes réglées, écart max 0.00%",
    "319357019": "PSI — 2026-10-02, 26 périodes réglées, écart max 0.00%",
    "726746629": "PSIL — 2026-10-02, 26 périodes réglées, écart max 0.03%",
    "320227571": "QQQ — 2026-10-02, 26 périodes réglées, écart max 0.00%",
    "319359375": "RSP — 2026-10-02, 52 périodes réglées, écart max 0.00%",
    "319359411": "RSPN — 2026-10-02, 26 périodes réglées, écart max 0.01%",
    "178813576": "SBIO — 2026-10-02, 52 périodes réglées, écart max 0.02%",
    "82817278": "SCHH — 2026-10-02, 26 périodes réglées, écart max 0.00%",
    "756733": "SPY — 2026-10-02, 26 périodes réglées, écart max 0.00%",
    "27684070": "VGK — 2026-10-02, 26 périodes réglées, écart max 0.00%",
    "27638082": "VHT — 2026-10-02, 52 périodes réglées, écart max 0.00%",
    "45540859": "XHB — 2026-10-02, 26 périodes réglées, écart max 0.00%",
    "4215200": "XLB — 2026-10-02, 52 périodes réglées, écart max 0.01%",
    "322317077": "XLC — 2026-10-02, 52 périodes réglées, écart max 0.00%",
    "4215217": "XLE — 2026-10-02, 52 périodes réglées, écart max 0.01%",
    "4215220": "XLF — 2026-10-02, 52 périodes réglées, écart max 0.00%",
    "4215227": "XLI — 2026-10-02, 52 périodes réglées, écart max 0.00%",
    "4215230": "XLK — 2026-10-02, 52 périodes réglées, écart max 0.00%",
    "4215210": "XLP — 2026-10-02, 52 périodes réglées, écart max 0.00%",
    "209048377": "XLRE — 2026-10-02, 52 périodes réglées, écart max 0.00%",
    "4215235": "XLU — 2026-10-02, 52 périodes réglées, écart max 0.01%",
    "4215205": "XLV — 2026-10-02, 52 périodes réglées, écart max 0.00%",
    "4215215": "XLY — 2026-10-02, 52 périodes réglées, écart max 0.01%",
    "413951498": "XOP — 2026-10-02, 52 périodes réglées, écart max 0.00%",
    "49954154": "ACWI — 2026-10-02 (P3), 52 périodes réglées, écart max 0.00%",
    "611584557": "COPJ — 2026-10-02 (P3), 52 périodes réglées, écart max 0.03%",
    "319355208": "DBC — 2026-10-02 (P3), 52 périodes réglées, écart max 0.00%",
    "73128548": "DIA — 2026-10-02 (P3), 52 périodes réglées, écart max 0.00%",
    "49954171": "EIS — 2026-10-02 (P3), 52 périodes réglées, écart max 0.01%",
    "75778782": "EPOL — 2026-10-02 (P3), 52 périodes réglées, écart max 0.00%",
    "2586606": "EWA — 2026-10-02 (P3), 52 périodes réglées, écart max 0.00%",
    "2586548": "EWC — 2026-10-02 (P3), 52 périodes réglées, écart max 0.00%",
    "2586603": "EWG — 2026-10-02 (P3), 52 périodes réglées, écart max 0.00%",
    "253190534": "EWJ — 2026-10-02 (P3), 52 périodes réglées, écart max 0.00%",
    "253190576": "EWT — 2026-10-02 (P3), 52 périodes réglées, écart max 0.00%",
    "253190561": "EWU — 2026-10-02 (P3), 52 périodes réglées, écart max 0.00%",
    "2586566": "EWW — 2026-10-02 (P3), 52 périodes réglées, écart max 0.00%",
    "10753248": "EWY — 2026-10-02 (P3), 52 périodes réglées, écart max 0.00%",
    "10753244": "EWZ — 2026-10-02 (P3), 52 périodes réglées, écart max 0.00%",
    "676783301": "FBTC — 2026-10-02 (P3), 52 périodes réglées, écart max 0.01%",
    "39622928": "FDN — 2026-10-02 (P3), 52 périodes réglées, écart max 0.00%",
    "229726316": "GDX — 2026-10-02 (P3), 52 périodes réglées, écart max 0.00%",
    "229726197": "GDXJ — 2026-10-02 (P3), 52 périodes réglées, écart max 0.00%",
    "51529211": "GLD — 2026-10-02 (P3), 52 périodes réglées, écart max 0.00%",
    "543859629": "GLDM — 2026-10-02 (P3), 52 périodes réglées, écart max 0.00%",
    "280803962": "GOAU — 2026-10-02 (P3), 52 périodes réglées, écart max 0.03%",
    "95053797": "GUNR — 2026-10-02 (P3), 52 périodes réglées, écart max 0.00%",
    "680623548": "HACK — 2026-10-02 (P3), 52 périodes réglées, écart max 0.00%",
    "43652089": "HYG — 2026-10-02 (P3), 52 périodes réglées, écart max 0.00%",
    "39046988": "IAI — 2026-10-02 (P3), 52 périodes réglées, écart max 0.00%",
    "474829650": "IAU — 2026-10-02 (P3), 52 périodes réglées, écart max 0.00%",
    "15547844": "IEF — 2026-10-02 (P3), 52 périodes réglées, écart max 0.00%",
    "39046982": "IHF — 2026-10-02 (P3), 52 périodes réglées, écart max 0.00%",
    "101484826": "INDA — 2026-10-02 (P3), 52 périodes réglées, écart max 0.00%",
    "39046959": "ITA — 2026-10-02 (P3), 52 périodes réglées, écart max 0.00%",
    "9579970": "IWM — 2026-10-02 (P3), 52 périodes réglées, écart max 0.00%",
    "26337175": "IYT — 2026-10-02 (P3), 52 périodes réglées, écart max 0.01%",
    "45540769": "KBE — 2026-10-02 (P3), 52 périodes réglées, écart max 0.00%",
    "45540822": "KRE — 2026-10-02 (P3), 52 périodes réglées, écart max 0.00%",
    "86326988": "MCHI — 2026-10-02 (P3), 52 périodes réglées, écart max 0.02%",
    "229728912": "MOO — 2026-10-02 (P3), 52 périodes réglées, écart max 0.00%",
    "415578515": "OIH — 2026-10-02 (P3), 52 périodes réglées, écart max 0.00%",
    "625287738": "OUST — 2026-10-02 (P3), 52 périodes réglées, écart max 0.00%",
    "268960148": "PAVE — 2026-10-02 (P3), 52 périodes réglées, écart max 0.00%",
    "253190574": "RING — 2026-10-02 (P3), 52 périodes réglées, écart max 0.00%",
    "319359417": "RSPH — 2026-10-02 (P3), 52 périodes réglées, écart max 0.03%",
    "374674771": "SGDM — 2026-10-02 (P3), 52 périodes réglées, écart max 0.01%",
    "211651690": "SIL — 2026-10-02 (P3), 52 périodes réglées, écart max 0.00%",
    "680887855": "SILJ — 2026-10-02 (P3), 52 périodes réglées, écart max 0.00%",
    "334909235": "SIVR — 2026-10-02 (P3), 52 périodes réglées, écart max 0.00%",
    "39039301": "SLV — 2026-10-02 (P3), 52 périodes réglées, écart max 0.00%",
    "101795139": "SLVP — 2026-10-02 (P3), 52 périodes réglées, écart max 0.00%",
    "229726273": "SLX — 2026-10-02 (P3), 52 périodes réglées, écart max 0.01%",
    "319359420": "TAN — 2026-10-02 (P3), 52 périodes réglées, écart max 0.00%",
    "26787475": "TIP — 2026-10-02 (P3), 52 périodes réglées, écart max 0.00%",
    "15547841": "TLT — 2026-10-02 (P3), 52 périodes réglées, écart max 0.00%",
    "211651685": "URA — 2026-10-02 (P3), 52 périodes réglées, écart max 0.00%",
    "319355766": "UUP — 2026-10-02 (P3), 52 périodes réglées, écart max 0.00%",
    "27684033": "VWO — 2026-10-02 (P3), 52 périodes réglées, écart max 0.00%",
    "543507571": "WGMI — 2026-10-02 (P3), 52 périodes réglées, écart max 0.00%",
    "45540699": "XME — 2026-10-02 (P3), 52 périodes réglées, écart max 0.00%",
    "45540784": "XRT — 2026-10-02 (P3), 52 périodes réglées, écart max 0.00%",
}






EODHD_EXCLUDED = {
    "50488867": "ENLAY — barres plates EODHD 10 séances sur 22 en 2026-09, écarts quotidiens jusqu'à 1 %",




    "88286963": "GLEN — mèches EODHD aberrantes en 2026-05/07 (hauts +14 %, bas −16 %) contre IBKR, ligne détenue",
    "10537": "NTTYY — barres plates EODHD 17 séances sur 22 en 2026-09",
    "426481133": "NSCIF — barres plates EODHD 21 séances sur 22 en 2026-09",



    "920538509": "BRTX — EODHD sert l'avant-regroupement 1:20 du 2026-09-08 non ajusté",
    "893073402": "LABT — EODHD sert l'avant-regroupement 1:10 du 2026-06-22 non ajusté",






    "939039659": "ENLV — EODHD sert l'avant-regroupement 1:16 du 2026-10-27 divisé deux fois (÷16)",
    "935943477": "REVB — EODHD sert l'avant-regroupement 1:7 du 2026-10-20 divisé deux fois (÷7)",
    "780402000": "JBIO — EODHD sert une autre société avant 2025-04 (prix ÷ 20 000)",
    "9900000010": "UNIUSD — UNI-USD.CC est un autre jeton (0,0002 $ contre 4 à 10 $)",






    "6858242": "TMICY — ADR OTC : 8 semaines sur 8 tranchées par Yahoo en faveur d'IBKR (EODHD 33,33 pour 32,31)",
    "641664154": "277810 — EODHD 480 000 en 2026-W28 et 2026-07, Yahoo et IBKR 453 500 et 433 000",
    "465157510": "688012 — EODHD sans l'attribution gratuite de 2026-05 (×1,49) : 370,0 contre 248,3 chez Yahoo et IBKR",
    "852120280": "ADIL — EODHD ÷25 depuis 2025-09 (0,35 contre 8,75 chez Yahoo et IBKR)",
    "29612135": "AI.PA — barres EODHD isolées fausses (2024-W23 154,8 contre 144,8 chez Yahoo)",
    "156871527": "ENX — barre EODHD fausse en 2025-W21 (146,9 contre 143,4 chez Yahoo, 144,0 chez IBKR)",
    "576945813": "FCM — LSE illiquide : IBKR, EODHD et Yahoo discordants sur 23 semaines en deux ans",
    "614039256": "FMET — LSE illiquide : IBKR, EODHD et Yahoo discordants sur 16 semaines en deux ans",
    "774092201": "QUBE — LSE illiquide : IBKR, EODHD et Yahoo discordants sur 9 semaines en deux ans",
}












OFFICIAL_CLOSE_OUTSIDE_RTH = frozenset({
    "SBF", "IBIS", "IBIS2", "EBS", "LSE", "LSEETF", "AEB", "ENEXT.BE", "CHINEXT",
})





DECLARED_INDEX_CODES = {
    "416730": ("FVX.INDX", None), "416748": ("IRX.INDX", 0.1),
    "416921": ("TNX.INDX", None), "416933": ("TYX.INDX", None),
    "13455763": ("VIX.INDX", None), "47511905": ("VIX3M.INDX", None),
}

TICKER = re.compile(r"^[A-Z0-9]+$")


def _day_before(iso):
    return (datetime.date.fromisoformat(iso) - datetime.timedelta(days=1)).isoformat()


def _load(path):
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def cache_symbols(cache=CACHE):
    """conid -> symbole interne, pour chaque série du cache."""
    found = {}
    for path in sorted(cache.glob("*.json")):
        if not path.stem.isdigit():
            continue
        found[path.stem] = json.loads(path.read_text(encoding="utf-8")).get("symbol")
    return found


def cache_divisor(conid, cache=CACHE):
    """Diviseur d'unité mineure déclaré par le cache (`scale.divisor`), ou None."""
    path = pathlib.Path(cache) / f"{conid}.json"
    if not path.exists():
        return None
    return (json.loads(path.read_text(encoding="utf-8")).get("scale") or {}).get("divisor")


def source_facts(*, ratio=None, baskets=None, sheets=None, contracts=None):
    """Place IBKR, devise et code TradingView par conid, lus dans les sources."""
    ratio = _load(RATIO_MANIFEST).get("instruments", {}) if ratio is None else ratio
    baskets = _load(BASKETS) if baskets is None else baskets
    if sheets is None:
        sheets = [json.loads(p.read_text(encoding="utf-8")).get("identity") or {}
                  for p in sorted(SHEETS.glob("*.json"))]
    facts = {}

    def entry(conid):
        return facts.setdefault(str(conid), {"sources": []})

    for symbol, item in ratio.items():
        if item.get("conid") is None:
            continue
        fact = entry(item["conid"])
        fact["sources"].append("ratio-universe")
        fact.setdefault("symbol", symbol)
        for key in ("exchange", "currency", "source"):
            if item.get(key):
                fact.setdefault(key, item[key])
    for members in baskets.values():
        if not isinstance(members, list):
            continue
        for member in members:
            fact = entry(member["conid"])
            if "baskets" not in fact["sources"]:
                fact["sources"].append("baskets")
            fact.setdefault("symbol", member.get("symbol"))
            if member.get("exchange"):
                fact.setdefault("exchange", member["exchange"])
            if member.get("tv"):
                fact.setdefault("tv", member["tv"])


    contracts = _load(TRANSITIONS) if contracts is None else contracts
    for key, item in contracts.items():
        if key.startswith("_") or not isinstance(item, dict):
            continue
        for side in ("previous", "successor"):
            member = item.get(side) or {}
            if member.get("conid") is None:
                continue
            fact = entry(member["conid"])
            fact.setdefault("symbol", member.get("symbol"))
            for field, target in (("exchange", "exchange"), ("tv", "tv")):
                if member.get(field):
                    fact.setdefault(target, member[field])
    known = set(EODHD_SUFFIX_BY_IBKR_EXCHANGE) | set(UNCONFIRMED_PLACES) | {"COINBASE"}
    for identity in sheets:
        if identity.get("conid") is None:
            continue
        fact = entry(identity["conid"])
        fact["sources"].append("fiche")
        if identity.get("tradingview_symbol"):
            fact["tv"] = identity["tradingview_symbol"]
        if identity.get("exchange") in known:
            fact.setdefault("exchange", identity["exchange"])
        if identity.get("currency"):
            fact.setdefault("currency", identity["currency"])
    return facts


def transitions(contracts=None):
    """Changements de contrat datés (`basket-contracts.json`) : conid -> bornes."""
    contracts = _load(TRANSITIONS) if contracts is None else contracts
    found = {}
    for key, item in contracts.items():
        if key.startswith("_") or not isinstance(item, dict):
            continue
        previous, successor = item.get("previous") or {}, item.get("successor") or {}
        effective = item.get("effective_on")
        if not (effective and previous.get("conid") and successor.get("conid")):
            continue
        if previous["conid"] == successor["conid"]:
            continue
        found[str(previous["conid"])] = {
            "to": _day_before(effective), "successor": successor["conid"],
            "kind": item.get("kind")}
        found[str(successor["conid"])] = {
            "from": effective, "predecessor": previous["conid"],
            "kind": item.get("kind")}
    return found


def eodhd_code(fact, symbol):
    """(code EODHD, base, motif de non-résolution) — un seul des deux est rempli."""
    exchange = fact.get("exchange")
    tv = fact.get("tv") or ""
    tv_prefix, _, tv_local = tv.partition(":")
    if fact.get("source") == "hyperliquid-spot":


        return None, None, "crypto Hyperliquid : aucun code EODHD vérifié"
    if exchange == "COINBASE" or fact.get("source") == "coinbase-spot":
        base = (symbol or "")[:-3] if (symbol or "").endswith("USD") else None
        if not base or not TICKER.match(base):
            return None, None, f"crypto au symbole non reconnu : {symbol!r}"
        return f"{base}-USD.CC", "crypto Coinbase -> paire USD", None
    from_ibkr = EODHD_SUFFIX_BY_IBKR_EXCHANGE.get(exchange)
    from_tv = EODHD_SUFFIX_BY_TV_PREFIX.get(tv_prefix) if tv_prefix else None
    if exchange in UNCONFIRMED_PLACES:
        return None, None, f"place {exchange} : {UNCONFIRMED_PLACES[exchange]}"
    if exchange and not from_ibkr:
        return None, None, f"place IBKR {exchange} sans correspondance EODHD établie"
    if tv_prefix and tv_prefix not in EODHD_SUFFIX_BY_TV_PREFIX:
        return None, None, f"place TradingView {tv_prefix} : couverture EODHD non confirmée"
    if from_ibkr and from_tv and from_ibkr != from_tv:
        return None, None, f"places en désaccord : IBKR {exchange}, TradingView {tv_prefix}"
    suffix = from_ibkr or from_tv
    if not suffix:
        return None, None, "place non renseignée dans les sources"
    base = tv_local or symbol
    if suffix == "HK" and base and base.isdigit():
        base = base.zfill(4)
    if not base or not TICKER.match(base):
        return None, None, f"ticker {base!r} hors alphabet simple (classe d'action ?)"
    basis = f"place IBKR {exchange}" if from_ibkr else f"place TradingView {tv_prefix}"
    if tv_local:
        basis += ", ticker TradingView"
    return f"{base}.{suffix}", basis, None


def eodhd_candidate(fact, symbol, reason):
    """Code à PROUVER par le contrôle croisé, jamais à interroger en collecte."""
    if not reason.startswith("place non renseignée") or fact.get("tv"):
        return None
    if fact.get("currency") not in (None, "USD") or not symbol or not TICKER.match(symbol):
        return None
    return f"{symbol}.US"


def build(*, cache=None, facts=None, contracts=None):
    """La table complète, une entrée par série du cache, triée par conid."""
    symbols = cache_symbols() if cache is None else cache
    facts = source_facts(contracts=contracts) if facts is None else facts
    moves = transitions(contracts)
    instruments = {}
    for conid in sorted(symbols, key=int):
        fact = facts.get(conid, {})
        symbol = symbols[conid] or fact.get("symbol")
        move = moves.get(conid, {})
        bounds = {key: move[key] for key in ("from", "to") if key in move}
        ibkr = {"symbol": symbol, **({"exchange": fact["exchange"]} if fact.get("exchange") else {}),
                **bounds}
        item = {"symbol": symbol, "ibkr": [ibkr]}
        if fact.get("currency"):
            item["currency"] = fact["currency"]
        item["tradingview"] = [{"symbol": fact["tv"], **bounds}] if fact.get("tv") else []
        declared = DECLARED_RENAMES.get(conid)
        if declared:
            item["ibkr"] = [{**row, **({"exchange": fact["exchange"]} if fact.get("exchange") else {})}
                            for row in declared["ibkr"]]
            item["tradingview"] = list(declared["tradingview"])
            item["rename_proof"] = declared["proof"]
        code, basis, reason = eodhd_code(fact, symbol)
        if declared and declared.get("eodhd"):
            item["eodhd"] = list(declared["eodhd"])
            item["eodhd_basis"] = f"renommage déclaré : {declared['proof']}"
            for key in ("successor", "predecessor"):
                if key in move:
                    item[key] = move[key]
            instruments[conid] = item
            continue
        index_divisor = None
        if conid in DECLARED_INDEX_CODES:
            index_code, index_divisor = DECLARED_INDEX_CODES[conid]
            code, basis, reason = index_code, "indice, prouvé par égalité des clôtures (2026-10-02)", None
        excluded = EODHD_EXCLUDED.get(conid)
        if code and excluded:
            code, reason = None, f"code {code} exclu : {excluded}"
        if code:
            row = {"symbol": code, **bounds}
            if index_divisor:
                row["divisor"] = index_divisor
            if code.endswith(".LSE"):


                divisor = cache_divisor(conid)
                if divisor:
                    row["divisor"] = divisor
            item["eodhd"] = [row]
            item["eodhd_basis"] = basis
        else:
            item["eodhd"] = []
            item["eodhd_unresolved"] = reason
            candidate = eodhd_candidate(fact, symbol, reason)
            if candidate and conid in PROVEN_CANDIDATES:
                item["eodhd"] = [{"symbol": candidate, **bounds}]
                item["eodhd_basis"] = f"candidat prouvé : {PROVEN_CANDIDATES[conid]}"
                del item["eodhd_unresolved"]
            elif candidate:
                item["eodhd_candidate"] = candidate
        for key in ("successor", "predecessor"):
            if key in move:
                item[key] = move[key]
        instruments[conid] = item
    return {
        "_meta": {
            "role": ("Identité multi-sources des séries du cache : conid -> codes IBKR, "
                     "EODHD et TradingView, avec dates de validité (`from`/`to`, absentes = "
                     "ouvertes)."),
            "generated_by": "python3 scripts/market_identity.py --build — jamais édité à la main",
            "rule": ("Ce qui n'est pas établi reste nommé dans `eodhd_unresolved`, sans code ; "
                     "`eodhd_candidate` est une hypothèse que seul "
                     "`eodhd_crosscheck.py --candidates` peut prouver. Le code à interroger "
                     "est celui valide à la date d'appel."),
        },
        "instruments": instruments,
    }


def load(path=IDENTITY):
    return _load(path).get("instruments", {})


def symbol_for(conid, provider, *, on=None, table=None):
    """Le code valide à la date `on` (défaut : aujourd'hui), ou None."""
    table = load() if table is None else table
    day = str(on or datetime.date.today())[:10]
    for row in (table.get(str(conid)) or {}).get(provider) or []:
        if row.get("from", "0000-00-00") <= day <= row.get("to", "9999-12-31"):
            return row
    return None






_EXCHANGES = None


def _identity_signature():
    try:
        stat = IDENTITY.stat()
    except OSError:
        return None
    return (stat.st_mtime_ns, stat.st_size)


def listing_exchange(conid, table=None):
    """Place de cotation IBKR du conid, lue dans la table d'identité."""
    global _EXCHANGES
    if table is None:
        signature = _identity_signature()
        if _EXCHANGES is None or _EXCHANGES[0] != signature:
            _EXCHANGES = (signature, {
                key: next((row.get("exchange") for row in item.get("ibkr") or []
                           if row.get("exchange")), None)
                for key, item in load().items()})
        return _EXCHANGES[1].get(str(conid))
    return next((row.get("exchange") for row in (table.get(str(conid)) or {}).get("ibkr") or []
                 if row.get("exchange")), None)


def outside_rth(conid, table=None):
    """Vrai si l'historique IBKR de ce conid doit inclure le fixing de clôture."""
    return listing_exchange(conid, table) in OFFICIAL_CLOSE_OUTSIDE_RTH


def summary(table):
    resolved = sum(1 for item in table.values() if item.get("eodhd"))
    reasons = {}
    for item in table.values():
        reason = item.get("eodhd_unresolved")
        if reason:
            key = reason.split(" : ")[0] if " : " in reason else reason
            reasons[key] = reasons.get(key, 0) + 1
    return resolved, reasons


def main(argv=None):
    parser = argparse.ArgumentParser(description="Table d'identité conid -> IBKR / EODHD / TradingView.")
    parser.add_argument("--build", action="store_true", help="régénère references/market-identity.json")
    parser.add_argument("--check", action="store_true", help="séries sans identité et motifs de non-résolution")
    parser.add_argument("--show", help="affiche l'entrée d'un conid ou d'un symbole")
    args = parser.parse_args(argv)
    if args.build:
        document = build()
        jsonio.write(IDENTITY, document)
        table = document["instruments"]
        resolved, _ = summary(table)
        print(f"{IDENTITY.relative_to(SKILL)} : {len(table)} séries, {resolved} code(s) EODHD établi(s)")
        return 0
    table = load()
    if args.show:
        key = args.show if args.show in table else next(
            (conid for conid, item in table.items() if item.get("symbol") == args.show.upper()), None)
        if key is None:
            print(f"aucune identité pour {args.show}")
            return 1
        print(json.dumps({key: table[key]}, ensure_ascii=False, indent=2))
        return 0
    missing = sorted(set(cache_symbols()) - set(table), key=int)
    resolved, reasons = summary(table)
    print(f"{len(table)} séries, {resolved} code(s) EODHD établi(s), {len(table) - resolved} non résolue(s)")
    for reason, count in sorted(reasons.items(), key=lambda pair: -pair[1]):
        print(f"  {count:5d}  {reason}")
    if missing:
        print(f"{len(missing)} série(s) du cache sans identité — relancer --build : {', '.join(missing[:20])}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
