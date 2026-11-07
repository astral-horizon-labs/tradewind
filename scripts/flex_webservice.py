"""Flex Web Service d'IBKR — le protocole seul, sans configuration ni archive."""
from __future__ import annotations

import re
import time
from typing import Any, Callable

BASE_URL = "https://ndcdyn.interactivebrokers.com/AccountManagement/FlexWebService"

HEADERS = {"User-Agent": "ibkr-dashboard-flex/1.0"}
POLL_STEPS = (5, 10, 20, 30, 30, 30)


def strip_messages(text: str) -> str:
    """Le CSV sans les lignes « MSG » qu'IBKR glisse avant l'en-tête."""
    lines = text.splitlines(keepends=True)
    kept = [line for line in lines if not line.lstrip().startswith(('"MSG"', "MSG,"))]
    return "".join(kept) if len(kept) != len(lines) else text


def xml_field(text: str, tag: str) -> str | None:
    match = re.search(rf"<{tag}>\s*([^<]+?)\s*</{tag}>", text)
    return match.group(1) if match else None


def xml_error(text: str) -> str:
    code = xml_field(text, "ErrorCode") or "?"
    message = xml_field(text, "ErrorMessage") or text[:200]
    return f"Flex Web Service erreur {code}: {message}"


def fetch_statement(token: str, query_id: str, fd: str | None = None, td: str | None = None,
                    *, get: Callable[..., Any] | None = None,
                    sleep: Callable[[float], None] = time.sleep) -> tuple[str | None, str | None]:
    """Tire le CSV d'une query : SendRequest, puis GetStatement sondé par paliers."""
    import httpx

    get = get or httpx.get
    params = {"t": token, "q": query_id, "v": "3"}
    if fd:
        params["fd"] = fd
    if td:
        params["td"] = td
    try:
        response = get(f"{BASE_URL}/SendRequest", params=params, headers=HEADERS, timeout=30)
    except httpx.HTTPError as error:
        return None, f"SendRequest injoignable ({error.__class__.__name__})"
    if xml_field(response.text, "Status") != "Success":
        return None, xml_error(response.text)
    reference = xml_field(response.text, "ReferenceCode")
    if not reference:
        return None, f"SendRequest sans ReferenceCode : {response.text[:200]}"

    statement_url = xml_field(response.text, "Url") or f"{BASE_URL}/GetStatement"

    last = ""
    for delay in POLL_STEPS:
        sleep(delay)
        try:
            response = get(statement_url, params={"t": token, "q": reference, "v": "3"},
                           headers=HEADERS, timeout=60)
        except httpx.HTTPError as error:
            last = f"GetStatement injoignable ({error.__class__.__name__})"
            continue
        body = response.text
        if body.lstrip().startswith("<"):

            last = xml_error(body)
            if "progress" not in body.lower():
                return None, last
            continue
        return strip_messages(body), None
    return None, f"rapport jamais prêt après {sum(POLL_STEPS)} s — dernier état : {last}"
