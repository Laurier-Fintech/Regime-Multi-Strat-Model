# Docs

All the project's process documents in one place.

| File | What it is |
|---|---|
| [SPRINTS.md](SPRINTS.md) | Sprint tracker: what's done, what's next, who owns it |
| [JACOB_PROGRESS.md](JACOB_PROGRESS.md) | Running sleeve implementation log: changes, checks, current status and next steps |
| [SLEEVE_RELEASE_2026-11-23.md](SLEEVE_RELEASE_2026-11-23.md) | Main publication scope, interface migrations, verification and remaining dependencies |
| [SLEEVE_TARGET_INTEGRATION.md](SLEEVE_TARGET_INTEGRATION.md) | Equity/volatility selection, funding, hedge and complete-target contracts; required adapters and execution boundaries |
| [Jacob sleeve implementation briefing](output/pdf/Jacob_Equity_and_Volatility_Sleeve_Briefing.pdf) | Shareable explanation of the algorithms, changes, significance, verification and remaining work for the project manager and lead |
| [LTG_Quant_Regime_MultiStrat_WhitePaper.docx](LTG_Quant_Regime_MultiStrat_WhitePaper.docx) | Our white paper: the strategy, architecture, regime engine, risk and costs |
| [LTG - Regime Shifts Implications for Dynamic Strategies corrected.pdf](<LTG - Regime Shifts  Implications for Dynamic Strategies  corrected.pdf>) | Kritzman, Page & Turkington (2012), "Regime Shifts". The closest published version of our regime idea |
| [diagrams/er_market_data.png](diagrams/er_market_data.png) | ER diagram of `market_data.duckdb` (inputs) |
| [diagrams/er_trading.png](diagrams/er_trading.png) | ER diagram of `trading.duckdb` (run records) |
| [output/charts/](output/charts/) | Charts from the test runs: regime moods (`regime_*.png`), NAV vs SPY and sleeve weights (`backtest_*.png`) |
| [output/diagnosis/](output/diagnosis/) | The stuck-states diagnosis (Nov 2026): progress log, findings and charts per feature |

Code documentation stays next to the code: every folder has its own README.
