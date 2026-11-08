# Tradewind — the MCP server for Interactive Brokers investors

Tradewind is a local MCP server for Claude Code and Codex. It reads your Interactive
Brokers account through its Flex report, read-only, and gives your assistant:

- your book at cost and its holdings;
- a two-year weekly chart of each holding, with your average cost and your plan levels,
  and of any symbol you are studying;
- one written plan per holding (thesis, what confirms it, what invalidates it, exit,
  add), tracked at every weekly close, with its review dates and its history;
- the risk of each holding and of the whole book if every exit is hit, holdings
  without an exit first;
- the 83 market baskets ranked against SPY after each close, the members of each ranked
  by strength, and relative strength against SPY or against the holding's basket;
- your NAV over time and your drawdowns, measured without deposits and withdrawals;
- market regime alerts, read as a move with a direction, not as a red light.

It sends no orders. Your account and your plans stay on your machine; only the IBKR
identifier (conid) of a symbol goes to our price server when a chart or a comparison
needs its prices.

## Install

Ten minutes in the IBKR portal to create a Flex token and query
(`wallet_mcp/CLIENT.md`), then, with Python 3.11 or newer:

```bash
git clone https://github.com/astral-horizon-labs/tradewind.git
cd tradewind
python3 wallet_mcp/install_client.py --check
```

The installer asks for the token and the query ID, obtains its price server key by
itself, registers the `tradewind` server in Claude Code and Codex, then fetches your
book a first time. Then ask: "give me a rundown of my book".

Questions and feedback: this repository's issues.
