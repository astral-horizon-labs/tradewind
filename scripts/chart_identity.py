"""Identité commune aux liens TradingView et aux prix du graphique Wallet."""
from __future__ import annotations

import json
import re

import instrument_store
import market_identity
from derived_cache import DerivedCache, files_signature


EXCHANGES = {
    "AMEX": "AMEX", "ARCA": "AMEX", "NYSEARCA": "AMEX", "NYSE ARCA": "AMEX",
    "NASDAQ": "NASDAQ", "NASDAQ / NASDAQ TEXAS": "NASDAQ", "NYSE": "NYSE",
    "BATS": "CBOE", "CBOE": "CBOE", "PINK": "OTC", "OTC": "OTC",
    "COINBASE": "COINBASE", "COINBASE / ETHEREUM ERC-20": "COINBASE",
    "COINBASE / ETHEREUM ERC-677": "COINBASE",


    "CRYPTO": "CRYPTO",


    "IBIS": "XETR", "IBIS2": "XETR", "XETR": "XETR", "XETRA / IBIS": "XETR",
    "FWB2": "FWB", "FWB": "FWB", "GETTEX": "GETTEX",

    "SBF": "EURONEXT", "AEB": "EURONEXT", "ENEXT.BE": "EURONEXT", "EURONEXT": "EURONEXT",
    "LSE": "LSE", "LSEETF": "LSE",
    "BVME": "MIL", "BVME.ETF": "MIL", "MIL": "MIL",
    "EBS": "SIX", "SIX": "SIX", "SIX SWISS EXCHANGE": "SIX",
    "TSE": "TSX", "TSX": "TSX", "TSEJ": "TSE",
    "OSE": "OSL", "OSL": "OSL", "SEHK": "HKEX", "HKEX": "HKEX",
    "NASDAQ HELSINKI": "OMXHEX", "OMXHEX": "OMXHEX",
    "WSE": "GPW", "GPW": "GPW", "ASX": "ASX", "TASE": "TASE",
}





CURRENCY_BY_CHART_EXCHANGE = {
    "AMEX": "USD", "NASDAQ": "USD", "NYSE": "USD", "CBOE": "USD", "OTC": "USD",
    "COINBASE": "USD", "CRYPTO": "USD", "XETR": "EUR", "FWB": "EUR", "GETTEX": "EUR",
    "EURONEXT": "EUR", "MIL": "EUR", "OMXHEX": "EUR", "TSX": "CAD", "TSE": "JPY",
    "HKEX": "HKD", "SIX": "CHF", "ASX": "AUD", "GPW": "PLN",
}


def quote_currency(identity: dict, manifest: dict, exchange: str | None) -> str | None:
    """Devise de cotation : fiche, puis place IBKR, puis place du graphique ; None si inconnue."""
    for currency in (identity.get("currency"),
                     market_identity.exchange_currency(identity.get("exchange")),
                     manifest.get("currency"),
                     market_identity.exchange_currency(manifest.get("exchange")),
                     CURRENCY_BY_CHART_EXCHANGE.get(exchange or "")):
        if isinstance(currency, str) and re.fullmatch(r"[A-Z]{3}", currency):
            return currency
    return None


def load_universe() -> dict:
    """Les instruments du manifeste, lus sans `chart_ratios` : celui-ci résout"""
    return json.loads(market_identity.RATIO_MANIFEST.read_text(encoding="utf-8"))["instruments"]


def tradingview_exchange(value: object) -> str | None:
    """Normalise une place connue ; un libellé inconnu reste inconnu."""
    return EXCHANGES.get(value.strip().upper()) if isinstance(value, str) else None


def resolve_chart_identity(ticker: str, *, sheet: dict | None = None,
                           universe: dict | None = None) -> dict:
    """Rapproche les deux lecteurs sans écrire ni deviner une place absente."""
    ticker = ticker.strip().upper()
    if not re.fullmatch(r"[A-Z0-9._-]+", ticker):
        raise ValueError("symbole du graphique invalide")
    if sheet is None:
        path = instrument_store.SHEETS / f"{ticker}.json"
        sheet = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    if universe is None:
        universe = load_universe()
    identity = sheet.get("identity") or {}
    manifest = universe.get(ticker) or {}
    conid = identity.get("conid") or manifest.get("conid")
    compatible = not (identity.get("conid") and manifest.get("conid")
                      and str(identity["conid"]) != str(manifest["conid"]))
    exchange = tradingview_exchange(identity.get("exchange"))
    if not exchange and compatible:
        exchange = tradingview_exchange(manifest.get("exchange"))
    qualified = f"{exchange}:{ticker}" if exchange else ticker
    override = identity.get("tradingview_symbol")
    if isinstance(override, str) and re.fullmatch(r"[A-Z0-9._-]+:[A-Z0-9._-]+", override):
        qualified = override
        exchange = override.split(":", 1)[0]
    return {
        "ticker": ticker,
        "symbol": qualified,
        "exchange": exchange,
        "conid": conid,
        "name": identity.get("name") or manifest.get("name") or ticker,
        "currency": quote_currency(identity, manifest if compatible else {}, exchange),
    }


_ALIAS_INDEX = DerivedCache(max_entries=2)


def _alias_index() -> dict:
    """{tradingview_symbol: [(symbole, fiche)]}, mémoïsé par signature des fiches."""
    sheets = instrument_store.SHEETS

    def build() -> dict:
        index: dict[str, list] = {}
        for path in sorted(sheets.glob("*.json")):
            sheet = json.loads(path.read_text(encoding="utf-8"))
            alias = (sheet.get("identity") or {}).get("tradingview_symbol")
            if alias:
                index.setdefault(alias, []).append((sheet.get("symbol") or path.stem, sheet))
        return index

    return _ALIAS_INDEX.get(
        lambda: (str(sheets), files_signature(sheets.glob("*.json"))), build)


def resolve_chart_request(symbol: str, *, universe: dict | None = None) -> dict:
    """Rattache un alias TradingView explicite au contrat Wallet unique."""
    ticker = symbol.split(":", 1)[-1]
    direct = resolve_chart_identity(ticker, universe=universe)
    if direct["symbol"] == symbol:
        return direct
    matches = [resolve_chart_identity(name, sheet=sheet, universe=universe)
               for name, sheet in _alias_index().get(symbol, [])]
    if len(matches) == 1:
        return matches[0]
    if len(matches) > 1:
        raise ValueError("Plusieurs instruments Wallet désignent ce graphique.")
    return direct
