#!/usr/bin/env python3
"""MCP WALLET, MODE CLIENT — le livre d'un investisseur lu par son propre Flex.

    python wallet_mcp/client_server.py      serveur stdio (Claude Code, Codex, Claude Desktop)

POURQUOI UN SECOND SERVEUR (2026-11-07). `server.py` sert le livre du propriétaire
par son backend (`:8000`, Gateway, planificateur) ; un client n'a rien de tout cela.
Celui-ci ne parle qu'à IBKR, par le Flex Web Service et le jeton du client
(`client_book.py`), et garde le rapport sur la machine du client. Les deux serveurs
restent séparés plutôt qu'un seul à deux modes : un client ne doit jamais voir un
outil qui chercherait un backend qu'il n'a pas.

LOT 1 : le livre au coût (`book_summary`, `positions`) et l'état de la configuration
(`setup_status`). LOT 2 (même jour) : le graphique hebdomadaire d'une ligne
(`weekly_chart`), sur les prix de NOTRE serveur (`client_prices.py`), décision du
propriétaire. LOT 3 (même jour) : le plan de chaque ligne (`plan`, `set_plan`,
`plans_overview`), écrit chez le client et suivi sur nos prix (`client_plans.py`).
LOT 4 (même jour) : les alertes de régime de la méthode (`regime_alerts`), évaluées sur
nos prix (`client_regime.py`).

CE QU'IL NE FAIT PAS : aucun ordre, aucune écriture hors de la machine du client (son
cache local et les plans de son livre, sous son répertoire de données). Ce qui sort de la machine : la requête Flex vers IBKR, et
vers notre serveur de prix le seul conid de la ligne dont on demande le graphique —
ni quantité, ni coût, ni valeur.
"""
from __future__ import annotations

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from mcp.server.mcpserver import Image, MCPServer  # noqa: E402

import client_book  # noqa: E402
import client_plans  # noqa: E402
import client_regime  # noqa: E402

INSTRUCTIONS = """\
The user's investment book, read from IBKR through their Flex report, read-only.
For any question about their portfolio, call THESE tools first.
Rules:
- The Flex report is the last session IBKR has processed (nightly batch): quote `date`
  with every figure, and `notes` when they say data is missing or a fetch failed.
- Weights are read at COST (`weight_cost_pct`): the money committed per holding; the
  market value (`weight_value_pct`) says what the market made of it.
- Without a Cash Report query, NAV and cash are `null`: never infer them from positions.
- No opinion on a holding without looking at `weekly_chart` first: the image first, the
  figures that come with it second. The current week is not drawn.
- Every holding has a plan: thesis, what confirms it (`if_hit`), what invalidates it
  (`if_miss`), the next decision, and at least one exit level. A holding without a plan
  or without an exit gets one with `set_plan`, after `weekly_chart`. Levels are
  horizontal, judged on the weekly close, and justified by the visible candles.
- Call `plans_overview` at the start of a conversation: whatever crossed a level comes
  before anything else, and its `if_miss` says what the plan intended.
- A regime alert lags by construction: talking about it means saying where the move is
  heading (`direction`, `recent_settled`), what it changes for the affected holdings and
  what would confirm it, in plain words. Name one alert only if it teaches something,
  never "everything is red". No sale on that signal alone: exits are the plans' exits.
- Call `setup_status` first when a tool returns a configuration error.
- Answer in the user's language.
- This server sends no orders and writes nothing at IBKR.
"""

mcp = MCPServer("tradewind", instructions=INSTRUCTIONS, log_level="WARNING")


@mcp.tool(description='The book at a glance: session date, NAV and cash (when the cash report is configured), total cost, number of holdings, top ten holdings by weight at cost. `refresh=True` fetches the report from IBKR even if it is under six hours old (~30 s).')
def book_summary(refresh: bool = False) -> dict:
    """Le livre en un coup d'œil : date de la séance, NAV et cash (si le rapport cash est
    configuré), coût total, nombre de lignes, dix premières lignes par poids au coût.
    `refresh=True` retire le rapport chez IBKR même s'il a moins de six heures (~30 s)."""
    return client_book.book_summary(force=refresh)


@mcp.tool(description='Every holding, in base currency: quantity, cost, value, weight at cost and at value, unrealized P&L. Sorted by weight at cost, descending.')
def positions() -> dict:
    """Toutes les lignes, en devise de base : quantité, coût, valeur, poids au coût et à
    la valeur, plus-value latente. Triées par poids au coût décroissant."""
    return client_book.positions()


@mcp.tool(description='The client configuration (file, cash report, base currency) and the age of the cached report. Fetches nothing from IBKR and never reveals the token.')
def setup_status() -> dict:
    """La configuration du client (fichier, rapport cash, devise de base) et l'âge du
    rapport gardé. Ne tire rien chez IBKR et ne révèle jamais le jeton."""
    return client_book.setup_status()


# Sans sortie structurée : l'image suivie de son texte se rend en deux blocs de contenu.
@mcp.tool(structured_output=False, description="Two-year weekly chart of a holding (settled candles, log scale), with the client's average cost as blue dashes and the plan levels as solid lines. Look at it before any opinion. Grid prices and the last settled close come alongside.")
def weekly_chart(symbol: str) -> list | dict:
    """Graphique hebdomadaire sur deux ans d'une ligne détenue (bougies réglées, échelle
    log), avec le coût moyen du client en tirets bleus. À regarder avant tout avis.
    Les prix des lignes de la grille et la dernière clôture réglée sont rendus à côté."""
    result = client_book.weekly_chart(symbol)
    if "error" in result:
        return result
    png = result.pop("png")
    return [Image(data=png, format="png"), result]


@mcp.tool(description="The method's market regime alerts on settled closes: triggered first, with their latest values, the direction of the move against the threshold, what they mean and what they ask for. Market data only, nothing from the account.")
def regime_alerts() -> dict:
    """Les alertes de régime de la méthode sur les clôtures réglées : franchies d'abord,
    avec leurs dernières valeurs, le sens du mouvement face au seuil, ce qu'elles
    veulent dire et ce qu'elles demandent. Données de marché seules, rien du compte."""
    return client_regime.regime_alerts()


@mcp.tool(description='Every holding against its plan, on settled closes: crossed levels (with what the plan intended), holdings without a plan, holdings without an exit, and the nearest exit of the others.')
def plans_overview() -> dict:
    """Chaque ligne détenue face à son plan, sur les clôtures réglées : niveaux franchis
    (avec ce que le plan prévoyait), lignes sans plan, lignes sans sortie, et la sortie
    la plus proche des autres."""
    return client_plans.overview()


@mcp.tool(description='The plan of one holding: thesis, conditions, next decision, and each level with its effective threshold, the last settled close and the distance.')
def plan(symbol: str) -> dict:
    """Le plan d'une ligne détenue : thèse, conditions, prochaine décision, et chaque
    niveau avec son seuil effectif, la dernière clôture réglée et la distance."""
    return client_plans.get_plan(symbol)


@mcp.tool(description='Writes the active plan of a holding, on the client\'s machine. `horizon`: long or short. One level per line: "1W < 140 (memory) [exit] exit on a weekly close below 140" — bar 1D|1W|1M, < or >, a price, `sma10` or `trail<seed>`, the method in parentheses (memory, fib, pivot, round, faber, net), the effect in brackets (exit, trim, add, warn, review), then the action. Without levels, `no_levels_reason` is required. An invalid plan is rejected as a whole, with all its violations.')
def set_plan(symbol: str, thesis: str, horizon: str, if_hit: str, if_miss: str,
             next_decision: str, levels: list[str] | None = None,
             no_levels_reason: str | None = None, review_by: str | None = None,
             reason: str | None = None) -> dict:
    """Écrit le plan actif d'une ligne détenue, chez le client. `horizon` : long ou short.
    Chaque niveau en une ligne : « 1W < 140 (memory) [exit] sortie si clôture hebdo sous
    140 » — barre 1D|1W|1M, < ou >, un prix, `sma10` ou `trail<seed>`, la méthode entre
    parenthèses (memory, fib, pivot, round, faber, net), l'effet entre crochets (exit,
    trim, add, warn, review), puis l'action. Sans niveau, `no_levels_reason` est exigé.
    Un plan invalide est refusé en entier, avec toutes ses violations."""
    return client_plans.set_plan(symbol, thesis, horizon, if_hit, if_miss, next_decision,
                                 levels, no_levels_reason, review_by, reason)


if __name__ == "__main__":
    mcp.run()
