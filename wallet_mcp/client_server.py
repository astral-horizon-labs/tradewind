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
nos prix (`client_regime.py`). LOT 6 (même jour, « tous les tools possibles ») : le
marché (`relative_strength`, `basket`, `weekly_chart` d'un titre non détenu,
`client_market.py`), le risque face aux sorties (`position_risk`, `book_risk`), les
revues (`reviews_due`, `plan_history`, `client_risk.py`), la NAV et ses creux
(`nav_history`, `drawdowns`, `client_nav.py`, deux requêtes Flex facultatives).

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
import client_market  # noqa: E402
import client_nav  # noqa: E402
import client_plans  # noqa: E402
import client_regime  # noqa: E402
import client_risk  # noqa: E402

INSTRUCTIONS = """\
The user's investment book, read from IBKR through their Flex report, read-only.
For any question about their portfolio, call THESE tools first.
Rules:
- The Flex report is the last session IBKR has processed (nightly batch): quote `date`
  with every figure, and `notes` when they say data is missing or a fetch failed.
- Weights are read at COST (`weight_cost_pct`): the money committed per holding; the
  market value (`weight_value_pct`) says what the market made of it.
- Without a Cash Report query, NAV and cash are `null`: never infer them from positions.
- No opinion on a holding without looking at `weekly_chart` first, and at its
  `relative_strength` against its basket or SPY: the image first, the figures that come
  with it second. The current week is not drawn. `weekly_chart` also draws a symbol the
  user does not hold (an idea, a basket member).
- From the market down to the stock: for a new idea, `basket_ranking` first (which
  baskets lead SPY), then `basket` for the leaders inside one, then the stock's chart.
- A holding is judged against its market first: rising less than its basket or SPY means
  the market is not carrying the bet, even in a rise.
- Risk is the money lost if a holding goes to its exit (`position_risk`, `book_risk`). A
  holding without a written exit has unbounded risk: say it first.
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
@mcp.tool(structured_output=False, description="Two-year weekly chart of a holding (settled candles, log scale), with the client's average cost as blue dashes and the plan levels as solid lines; also any symbol of the market universe or the baskets the user does not hold. Look at it before any opinion. Grid prices and the last settled close come alongside.")
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


def with_image(result: dict) -> list | dict:
    if "error" in result:
        return result
    png = result.pop("png")
    return [Image(data=png, format="png"), result]


@mcp.tool(structured_output=False, description='A symbol against a benchmark: the weekly ratio drawn over two years (a rising line means the symbol leads), its performance spread over 4, 13, 26 and 52 weeks, the ratio against its 10-week average and its trend over the last five weeks. `against`: a symbol (default SPY, or QQQ, XLV, IWM…) or "basket" for the equal-weight basket the symbol belongs to. Works for holdings and for any symbol of the market universe or the baskets.')
def relative_strength(symbol: str, against: str = "SPY") -> list | dict:
    """Le titre face à un repère : ratio hebdomadaire dessiné, écart sur 4 à 52 semaines,
    ratio face à sa moyenne de dix semaines. `against` : un symbole ou « basket »."""
    return with_image(client_market.relative_strength(symbol, against))


@mcp.tool(description='A market basket (e.g. "AI", "CNS BIOTECH", "AEROSPACE & DEFENSE"), named or found through one of its members: its members ranked by 13-week strength, and the equal-weight basket against SPY over 4 to 52 weeks. An unknown name lists the 83 baskets.')
def basket(name_or_symbol: str) -> dict:
    """Un panier, nommé ou désigné par un membre : membres classés par force sur 13
    semaines, et le panier équipondéré face au S&P 500. Un nom inconnu liste les paniers."""
    return client_market.basket(name_or_symbol)


@mcp.tool(description='Every market basket (83) ranked against SPY on settled weekly closes: the equal-weight basket\'s spread over 4, 13, 26 and 52 weeks, its ratio to SPY against its 10-week average, the direction of that ratio over five weeks, and its three strongest and weakest members over 13 weeks. Computed on our server after each close, read in one request. Start here to find the baskets that lead before choosing a stock.')
def basket_ranking() -> dict:
    """Les 83 paniers classés face au S&P 500, calculés par notre serveur après chaque clôture."""
    return client_market.ranking()


@mcp.tool(description='What a holding costs if it goes to its nearest exit: the exit threshold and its distance, the loss in base currency and as a share of the book, and the P&L left at the exit. A holding without a plan or without an exit has unbounded risk.')
def position_risk(symbol: str) -> dict:
    """Ce que coûte une ligne si elle va jusqu'à sa sortie la plus proche, en devise de
    base et en part du livre. Sans plan ni sortie : risque non borné."""
    return client_risk.position_risk(symbol)


@mcp.tool(description='The whole book against its exits: holdings with unbounded risk first (no plan or no exit), then the loss to exit of every other holding, and the total loss if every exit is hit.')
def book_risk() -> dict:
    """Le livre face à ses sorties : les lignes au risque non borné d'abord, puis la perte
    jusqu'à la sortie de chaque autre ligne, et la perte si toutes les sorties tombent."""
    return client_risk.book_risk()


@mcp.tool(description='Plans to re-read: review date passed, review within two weeks, plans without a review date (flagged stale after 180 days), and holdings without a plan.')
def reviews_due() -> dict:
    """Les plans à relire : revue dépassée, proche, plans sans date de revue (anciens
    au-delà de 180 jours), lignes sans plan."""
    return client_risk.reviews_due()


@mcp.tool(description="Every rewrite of a symbol's plan on this machine, newest first, with the current plan.")
def plan_history(symbol: str) -> dict:
    """Chaque réécriture du plan d'un titre, la plus récente d'abord, et le plan actuel."""
    return client_risk.plan_history(symbol)


@mcp.tool(description='Account value over time (needs the optional NAV and Cash Transactions Flex queries): month-end NAV, a growth index without deposits and withdrawals, its peak, every deposit and withdrawal. `refresh=True` fetches the reports again.')
def nav_history(refresh: bool = False) -> dict:
    """La NAV en fins de mois, l'indice sans flux et son sommet, chaque apport et retrait
    (requêtes Flex NAV et Cash Transactions facultatives)."""
    return client_nav.nav_history(refresh_now=refresh)


@mcp.tool(description='The book\'s drawdown from its peak, measured without deposits and withdrawals, its worst point, and past episodes of at least 5% with their median: context, not a threshold. Needs the optional NAV Flex query.')
def drawdowns() -> dict:
    """La baisse du livre depuis son sommet, sans les flux, son pire point et les creux
    passés d'au moins 5 % avec leur médiane : du contexte, pas un seuil."""
    return client_nav.drawdowns()


if __name__ == "__main__":
    mcp.run()
