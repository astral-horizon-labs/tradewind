# Tradewind in Claude Code or Codex — installation

The Tradewind MCP server reads your Interactive Brokers account through its Flex report,
read-only, and gives you, inside your assistant:

- your book at cost and its holdings (`book_summary`, `positions`);
- a two-year weekly chart of each holding, with your average cost and your plan levels,
  and of any symbol you are studying (`weekly_chart`);
- one plan per holding, written by the assistant and tracked at every weekly close:
  thesis, what confirms it, what invalidates it, exit and add levels (`set_plan`,
  `plan`, `plans_overview`), with its review dates and history (`reviews_due`,
  `plan_history`);
- what each holding costs if it goes to its exit, and the whole book if every exit is
  hit, holdings without an exit first (`position_risk`, `book_risk`);
- the 83 market baskets ranked against SPY, computed on our server after each close
  (`basket_ranking`), the members of one basket ranked by strength (`basket`), and
  relative strength against SPY or against the holding's basket (`relative_strength`);
- your NAV over time and your drawdowns, without deposits and withdrawals (`nav_history`,
  `drawdowns`, two optional queries);
- the market regime alerts (`regime_alerts`).

It sends no orders. Your account never leaves your machine: the Flex report and your
plans stay there. Only the IBKR identifier (conid) of a symbol goes to our price server
when a chart or a comparison needs its prices.

## 1. Create Flex access in the IBKR portal (ten minutes, once)

IBKR portal → **Performance & Reports** → **Flex Queries**.

1. **The token**: *Flex Web Service Configuration* tab, enable it and generate a token.
   Pick its lifetime (one year at most) and note the date: you will need to renew it.
2. **The positions query** (required): *Activity Flex Query* → **Create**.
   - **Open Positions** section, options: level of detail **Lot** (*Summary* must also
     appear);
   - columns: `ClientAccountID`, `LevelOfDetail`, `ReportDate`, `Symbol`, `Conid`,
     `Quantity`, `MarkPrice`, `PositionValue`, `CostBasisMoney`, `CostBasisPrice`,
     `FXRateToBase`, `CurrencyPrimary`, `ListingExchange`, `AssetClass`;
   - format **CSV**, column headers included, dates **yyyyMMdd**, period
     **Last Business Day**. Only one section in this query.
   - Save, then note its **Query ID**.
3. **The Cash Report query** (optional, for NAV and cash): a second *Activity Flex
   Query*, **Cash Report** section only, columns `ClientAccountID`, `CurrencyPrimary`,
   `EndingCash` and `ToDate`, same settings. Note its Query ID.

4. **NAV history and drawdowns** (optional, two more queries, same settings except the
   period **Last 365 Days**):
   - *Activity Flex Query* with the **Net Asset Value (NAV) in Base** section only,
     option **Breakout by Day**, columns `ClientAccountID`, `ReportDate`, `Total`;
   - *Activity Flex Query* with the **Cash Transactions** section only, type
     **Deposits & Withdrawals**, columns `ClientAccountID`, `Date/Time`, `Amount`,
     `FXRateToBase`, `Type`, `Description`.

   IBKR serves one year at a time; every daily fetch is kept, so the history lengthens.

## 2. Install (one command)

Python 3.11 or newer. In the repository folder:

```bash
python3 wallet_mcp/install_client.py --check
```

The command asks for the token and the query IDs (`--query-id-nav` and
`--query-id-cashtx` add the NAV queries later). It obtains its price server key by
itself, installs the server's dependency, writes `~/.config/wallet/client.json`
(readable by you only), registers the `tradewind` server in Claude Code and Codex when
they are installed, then fetches your book a first time.

Claude Desktop: add the command the installer prints (`.venv-client/bin/python` and
`wallet_mcp/client_server.py`) to `claude_desktop_config.json`.

## 3. First conversation

"Give me a rundown of my book", then "write the plan for my first holding". The
assistant looks at the chart before writing a plan; every level is judged on the weekly
close.

## If something goes wrong

- `setup_status` says what is missing from the configuration.
- **Flex error 1012 or 1015**: the token expired or is invalid; generate a new one and
  run the installer again with `--token`.
- **Flex error 1019**: the report is being generated; try again in a minute.
- **Base currency undetermined**: run again with `--base-currency USD` (or EUR…).
- Today's report only appears after IBKR's nightly processing: the book is the one of
  the last processed session, and every answer gives its date.
