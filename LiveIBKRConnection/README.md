# LiveIBKRConnection

## What this folder is for
This is the low-level connection to **Interactive Brokers (IBKR)**. It logs in, keeps the connection alive, asks for prices and account details, and sends or cancels orders. It holds **no trading logic** and makes no decisions. Other folders decide *what* to do and call this one to *do* it.

Two folders use it:
- [Execution](../Execution/), to place and manage orders.
- [Data/DataSources](../Data/DataSources/), to pull live prices and option chains.

Think of it as the phone line to the broker. It doesn't decide what to say. It just makes sure the call connects and the messages get through.

## Files that will live here (planned)
| File | What it does | Complexity |
|---|---|---|
| `connection.py` | Connects to IBKR's TWS or IB Gateway program, reconnects automatically if the line drops, and knows whether we're on the **paper** or **live** account. | Medium |
| `market_data.py` | Requests live prices, option chains and implied volatilities. | Medium |
| `account.py` | Reads positions, cash, margin and fills from IBKR. | Low–Medium |
| `orders.py` | Sends, changes and cancels orders exactly as given by [Execution](../Execution/). | Low–Medium |
| `contracts.py` | Looks up IBKR's own ID for each instrument (the "conId") and caches it in the contract master in [Common](../Common/). | Low–Medium |

## What it talks to
- **Gets from:** [Execution](../Execution/) (orders to send), [Data/DataSources](../Data/DataSources/) (data requests), and [Config](../Config/) (host, port, account ID; credentials come from the private `.env` file, which is never committed).
- **Hands to:** IBKR itself, and it returns prices, positions and fills to whoever asked.

## Complexity: Medium
The IBKR API works in the background (answers come back later rather than straight away) and has strict limits on how often you can ask for data. The code isn't long, but it needs careful handling of timing and errors.

## Watch-outs
1. **Paper and live accounts must be impossible to mix up.** Make the account choice explicit in [Config](../Config/) and print it loudly at startup.
2. **Respect rate limits**, or IBKR will throttle or disconnect you.
3. **IBKR provides no history for expired options.** Don't plan the backtest around it.

## Read first
White paper §1 (IBKR-tradable instruments) and §9 (options data availability).
