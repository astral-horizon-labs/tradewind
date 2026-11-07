#!/usr/bin/env python3
"""Installe le MCP wallet chez un client, en une commande.

    python3 wallet_mcp/install_client.py                       questions posées une à une
    python3 wallet_mcp/install_client.py --token … --query-id … --prices-url … --prices-key …
    python3 wallet_mcp/install_client.py --check               puis tire le livre chez IBKR

POURQUOI (2026-11-07, lot 5 du MCP client). Le premier client visé travaille dans
Claude Code ou Codex. Entre le paquet téléchargé et une première question sur son
livre, il ne doit avoir qu'une commande à lancer et deux valeurs IBKR à coller.

CE QU'ELLE FAIT, dans l'ordre, et rien d'autre :
  1. un environnement Python à côté du paquet (`.venv-client`), avec la seule
     dépendance du MCP client (`requirements-client.txt`) ;
  2. la configuration `~/.config/wallet/client.json` (droits 600) : jeton et
     queries Flex, devise de base, adresse et clé du serveur de prix. Une valeur
     déjà présente est gardée, sauf si la commande en donne une nouvelle. Sans clé
     de prix, l'installeur en demande une au serveur (`POST /v1/keys`) : le client
     n'a rien à saisir de ce côté ;
  3. l'inscription du serveur dans Claude Code (`claude mcp add --scope user`) et
     dans Codex (`~/.codex/config.toml`), quand ils sont installés ;
  4. le contrôle : l'état de la configuration, et avec `--check` un premier tirage
     du livre chez IBKR.

Aucun secret n'est affiché : le jeton et la clé se saisissent sans écho.
"""
from __future__ import annotations

import argparse
import getpass
import json
import os
import pathlib
import shutil
import subprocess
import sys
import urllib.error
import urllib.request

HERE = pathlib.Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))
from client_messages import english  # noqa: E402  (bibliothèque standard seule)

PACKAGE = HERE.parent
VENV = PACKAGE / ".venv-client"
SERVER = HERE / "client_server.py"
REQUIREMENTS = HERE / "requirements-client.txt"
SERVER_NAME = "tradewind"
DEFAULT_PRICES_URL = "https://wallet-prices.kakobaba1212.workers.dev"
FIELDS = (  # (clé, drapeau, question, secret, obligatoire) ; question None : jamais posée
    ("token", "token", "Flex Web Service token", True, True),
    ("query_id", "query_id", "Flex query ID for positions (LOT)", False, True),
    ("query_id_cash", "query_id_cash", "Cash Report query ID (optional, for NAV)", False, False),
    ("base_currency", "base_currency", "Account base currency (optional, e.g. USD)", False, False),
    ("prices_url", "prices_url", None, False, False),
    ("prices_key", "prices_key", None, True, False),
)


def say(text: str) -> None:
    print(text, flush=True)


def config_path() -> pathlib.Path:
    configured = os.environ.get("WALLET_CLIENT_CONFIG")
    return pathlib.Path(configured).expanduser() if configured else (
        pathlib.Path.home() / ".config" / "wallet" / "client.json")


def venv_python() -> pathlib.Path:
    return VENV / ("Scripts/python.exe" if os.name == "nt" else "bin/python")


def ensure_venv() -> None:
    if not venv_python().exists():
        say(f"· Python environment: {VENV}")
        subprocess.run([sys.executable, "-m", "venv", str(VENV)], check=True)
    say("· MCP dependency (mcp)")
    subprocess.run([str(venv_python()), "-m", "pip", "install", "--quiet", "--disable-pip-version-check",
                    "-r", str(REQUIREMENTS)], check=True)


def write_private(path: pathlib.Path, text: str) -> None:
    """Écrit `text` en droits 600, par remplacement atomique."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
        handle.write(text)
    os.replace(temporary, path)


def collect(args, current: dict, ask: bool) -> tuple[dict, list[str]]:
    """La configuration fusionnée, et les champs obligatoires encore vides."""
    merged = dict(current)
    for key, flag, question, secret, _ in FIELDS:
        given = getattr(args, flag)
        if given:
            merged[key] = given.strip()
        elif ask and question and not merged.get(key):
            reader = getpass.getpass if secret else input
            answer = reader(f"  {question} : ").strip()
            if answer:
                merged[key] = answer
    missing = [key for key, _, _, _, required in FIELDS if required and not merged.get(key)]
    return merged, missing


def request_price_key(url: str, *, opener=urllib.request.urlopen) -> tuple[str | None, str | None]:
    """(clé, erreur) : une clé de lecture neuve, délivrée par le serveur de prix."""
    request = urllib.request.Request(f"{url.rstrip('/')}/v1/keys", data=b"", method="POST",
                                     headers={"User-Agent": "wallet-mcp-install"})
    try:
        with opener(request, timeout=30) as response:
            return json.loads(response.read().decode("utf-8"))["key"], None
    except urllib.error.HTTPError as failure:
        try:
            detail = json.loads(failure.read().decode("utf-8")).get("error")
        except (ValueError, AttributeError):
            detail = None
        return None, f"HTTP {failure.code}" + (f": {english(detail)}" if detail else "")
    except (urllib.error.URLError, OSError, ValueError, KeyError) as failure:
        return None, failure.__class__.__name__


def register_claude() -> str:
    claude = shutil.which("claude")
    if not claude:
        return "Claude Code not found: registration skipped"
    subprocess.run([claude, "mcp", "remove", "--scope", "user", SERVER_NAME],
                   capture_output=True, check=False)
    result = subprocess.run([claude, "mcp", "add", "--scope", "user", SERVER_NAME, "--",
                             str(venv_python()), str(SERVER)], capture_output=True, text=True, check=False)
    return ("Claude Code: \"wallet\" server registered" if result.returncode == 0
            else f"Claude Code: registration refused ({result.stderr.strip()[-200:]})")


def register_codex() -> str:
    folder = pathlib.Path.home() / ".codex"
    if not folder.exists():
        return "Codex not found: registration skipped"
    config = folder / "config.toml"
    text = config.read_text(encoding="utf-8") if config.exists() else ""
    header = f"[mcp_servers.{SERVER_NAME}]"
    if header in text:
        return f"Codex: {header} already in {config}, left as is"
    block = (f"\n{header}\ncommand = {json.dumps(str(venv_python()))}\n"
             f"args = [{json.dumps(str(SERVER))}]\n")
    write_private(config, text.rstrip("\n") + "\n" + block if text else block.lstrip("\n"))
    return f"Codex: {header} added to {config}"


def status(check: bool) -> int:
    code = ("import json, client_book; "
            "print(json.dumps(client_book.setup_status(), ensure_ascii=False)); "
            + ("s = client_book.book_summary(force=True); "
               "print('ERROR ' + s['error'] if 'error' in s else "
               "f\"book of {s['date']}: {s['line_count']} holdings, cost {s['total_cost']} {s['base_currency']}\")"
               if check else ""))
    result = subprocess.run([str(venv_python()), "-c", code], cwd=HERE, text=True,
                            capture_output=True, check=False)
    # La sortie ET, si le contrôle a planté, la fin de l'erreur : le 2026-11-07, un
    # `import httpx` manquant plantait après la première ligne, et le client ne lisait
    # que « the check failed: see the message above » sans aucun message au-dessus.
    say(result.stdout.strip())
    if result.returncode:
        say(result.stderr.strip()[-400:])
    return 1 if result.returncode or "ERROR" in result.stdout else 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Installs the Tradewind MCP server (Claude Code, Codex).")
    for _, flag, question, _, _ in FIELDS:
        parser.add_argument(f"--{flag.replace('_', '-')}", dest=flag, help=question or (
            "price server URL (ours by default)" if flag == "prices_url"
            else "price server key (requested from the server by default)"))
    parser.add_argument("--no-register", action="store_true",
                        help="do not register the server in Claude Code or Codex")
    parser.add_argument("--no-input", action="store_true",
                        help="ask nothing: a missing required field fails the install")
    parser.add_argument("--check", action="store_true",
                        help="fetch the book from IBKR after installing (about 30 s)")
    args = parser.parse_args(argv)

    path = config_path()
    try:
        current = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    except json.JSONDecodeError:
        say(f"⛔ {path} is unreadable: fix or remove it, then run again")
        return 1
    say("Flex and price server settings:")
    config, missing = collect(args, current, ask=not args.no_input and sys.stdin.isatty())
    if missing:
        say(f"⛔ missing required fields: {', '.join(missing)} — see wallet_mcp/CLIENT.md")
        return 1
    if not config.get("prices_key") and not config.get("prices_key_file"):
        key, error = request_price_key(config.get("prices_url") or DEFAULT_PRICES_URL)
        if error:
            say(f"⛔ price server key refused ({error}): try again later")
            return 1
        config["prices_key"] = key
        say("· price server key obtained")
    write_private(path, json.dumps({key: value for key, value in config.items() if value},
                                   indent=2, ensure_ascii=False) + "\n")
    say(f"· configuration: {path} (600)")

    ensure_venv()
    if not args.no_register:
        say("· " + register_claude())
        say("· " + register_codex())
    say("Check:")
    rc = status(args.check)
    say("Ready: in Claude Code or Codex, ask \"give me a rundown of my book\"."
        if rc == 0 else "⛔ the check failed: see the message above and wallet_mcp/CLIENT.md")
    return rc


if __name__ == "__main__":
    sys.exit(main())
