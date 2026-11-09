-- =============================================================================
-- trading.duckdb : schema (ONE-TIME, run by create_databases.py)
--
-- The record of what WE did: runs, regime probabilities, allocations, what the
-- sleeves wanted, positions, orders, fills, cash and NAV.
-- Written by ModelHome, Portfolio and Backtesting. Starts empty and fills up as
-- the system runs. Unlike market data it can NOT be rebuilt, so back it up.
--
-- Every record table starts with run_id, so backtest runs never overwrite
-- each other. as_of is the trading day the record belongs to.
--
-- Sleeve names match Config/configs.yaml: vol (A), equity (B), spread (C),
-- plus reserve.
-- =============================================================================

CREATE TABLE schema_version (
    db_name         VARCHAR   NOT NULL,          -- 'trading'
    schema_version  INTEGER   NOT NULL,
    duckdb_version  VARCHAR   NOT NULL,
    created_at      TIMESTAMP NOT NULL
);

-- One row per run (a backtest, or one paper/live session).
CREATE TABLE runs (
    run_id           VARCHAR   PRIMARY KEY,
    mode             VARCHAR   NOT NULL CHECK (mode IN ('backtest', 'paper', 'live')),
    git_commit       VARCHAR,
    config_snapshot  VARCHAR,                    -- the full settings used, as YAML/JSON text
    start_date       DATE,                       -- first trading day of the run
    end_date         DATE,
    started_at       TIMESTAMP NOT NULL,
    finished_at      TIMESTAMP,
    status           VARCHAR   NOT NULL DEFAULT 'running' CHECK (status IN ('running', 'finished', 'failed')),
    notes            VARCHAR
);

-- Contract master: one row per instrument we ever hold or trade (not per run).
-- instrument_id is our own readable id, e.g. 'SPY' or 'SPY 2027-01-15 P 500'.
CREATE TABLE instruments (
    instrument_id  VARCHAR PRIMARY KEY,
    symbol         VARCHAR NOT NULL,             -- exchange symbol
    underlying     VARCHAR,                      -- series_id of the underlying (options/futures)
    asset_type     VARCHAR NOT NULL CHECK (asset_type IN ('stock', 'etf', 'index', 'option', 'future', 'fx', 'cash')),
    expiry         DATE,
    strike         DOUBLE,
    call_put       VARCHAR CHECK (call_put IN ('C', 'P')),
    multiplier     DOUBLE  NOT NULL DEFAULT 1,   -- e.g. 100 for a US equity option
    currency       VARCHAR NOT NULL DEFAULT 'USD',
    exchange       VARCHAR,
    ibkr_conid     BIGINT
);

-- Regime engine output: probability of each state, each day.
CREATE TABLE regime_probs (
    run_id       VARCHAR NOT NULL,
    as_of        DATE    NOT NULL,
    state        VARCHAR NOT NULL,               -- label, e.g. 'calm', 'stressed'
    probability  DOUBLE  NOT NULL CHECK (probability BETWEEN 0 AND 1),
    PRIMARY KEY (run_id, as_of, state)
);

-- Capital given to each sleeve and the reserve.
CREATE TABLE allocations (
    run_id         VARCHAR NOT NULL,
    as_of          DATE    NOT NULL,
    sleeve         VARCHAR NOT NULL CHECK (sleeve IN ('vol', 'equity', 'spread', 'reserve')),
    target_weight  DOUBLE  NOT NULL,             -- share of total NAV (0..1)
    capital        DOUBLE,                       -- dollars
    PRIMARY KEY (run_id, as_of, sleeve)
);

-- What each sleeve WANTED to hold, and what risk management approved.
CREATE TABLE target_positions (
    run_id             VARCHAR NOT NULL,
    as_of              DATE    NOT NULL,
    sleeve             VARCHAR NOT NULL CHECK (sleeve IN ('vol', 'equity', 'spread', 'reserve')),
    instrument_id      VARCHAR NOT NULL,
    wanted_quantity    DOUBLE  NOT NULL,         -- from the sleeve
    approved_quantity  DOUBLE,                   -- after RiskManagement
    PRIMARY KEY (run_id, as_of, sleeve, instrument_id)
);

-- Risk layer actions (cuts, vetoes, circuit breaker).
CREATE TABLE risk_events (
    run_id         VARCHAR NOT NULL,
    as_of          DATE    NOT NULL,
    event_no       INTEGER NOT NULL,             -- 1, 2, 3 ... within the day
    rule           VARCHAR NOT NULL,             -- e.g. 'vix_circuit_breaker', 'max_net_vega'
    action         VARCHAR NOT NULL,             -- e.g. 'cut', 'veto', 'flatten'
    sleeve         VARCHAR,
    instrument_id  VARCHAR,
    detail         VARCHAR,
    PRIMARY KEY (run_id, as_of, event_no)
);

-- Holdings at the end of each day.
CREATE TABLE positions (
    run_id         VARCHAR NOT NULL,
    as_of          DATE    NOT NULL,
    sleeve         VARCHAR NOT NULL CHECK (sleeve IN ('vol', 'equity', 'spread', 'reserve')),
    instrument_id  VARCHAR NOT NULL,
    quantity       DOUBLE  NOT NULL,             -- signed: negative = short
    avg_cost       DOUBLE,
    market_price   DOUBLE,
    market_value   DOUBLE,
    is_model_priced BOOLEAN NOT NULL DEFAULT FALSE,  -- TRUE when no market price, valued with a model
    PRIMARY KEY (run_id, as_of, sleeve, instrument_id)
);

CREATE TABLE orders (
    run_id         VARCHAR   NOT NULL,
    order_id       VARCHAR   NOT NULL,
    as_of          DATE      NOT NULL,
    sleeve         VARCHAR   NOT NULL CHECK (sleeve IN ('vol', 'equity', 'spread', 'reserve')),
    instrument_id  VARCHAR   NOT NULL,
    quantity       DOUBLE    NOT NULL,           -- signed: positive = buy
    order_type     VARCHAR   NOT NULL DEFAULT 'market' CHECK (order_type IN ('market', 'limit')),
    limit_price    DOUBLE,
    status         VARCHAR   NOT NULL DEFAULT 'submitted' CHECK (status IN ('submitted', 'filled', 'partial', 'cancelled', 'rejected')),
    created_at     TIMESTAMP NOT NULL,
    broker_ref     VARCHAR,                      -- IBKR order id when live
    PRIMARY KEY (run_id, order_id)
);

CREATE TABLE fills (
    run_id           VARCHAR   NOT NULL,
    fill_id          VARCHAR   NOT NULL,
    order_id         VARCHAR,                    -- NULL for expiry / assignment
    as_of            DATE      NOT NULL,
    sleeve           VARCHAR   NOT NULL CHECK (sleeve IN ('vol', 'equity', 'spread', 'reserve')),
    instrument_id    VARCHAR   NOT NULL,
    quantity         DOUBLE    NOT NULL,         -- signed: positive = bought
    price            DOUBLE    NOT NULL,
    commission       DOUBLE    NOT NULL DEFAULT 0,
    fees             DOUBLE    NOT NULL DEFAULT 0,
    fill_type        VARCHAR   NOT NULL DEFAULT 'trade' CHECK (fill_type IN ('trade', 'expiry', 'assignment', 'exercise')),
    is_model_priced  BOOLEAN   NOT NULL DEFAULT FALSE,  -- TRUE for backtest option prices rebuilt from a model
    filled_at        TIMESTAMP,
    PRIMARY KEY (run_id, fill_id)
);

-- Every cash movement.
CREATE TABLE cash_ledger (
    run_id     VARCHAR NOT NULL,
    entry_id   VARCHAR NOT NULL,
    as_of      DATE    NOT NULL,
    sleeve     VARCHAR CHECK (sleeve IN ('vol', 'equity', 'spread', 'reserve')),
    amount     DOUBLE  NOT NULL,                 -- signed: positive = cash in
    kind       VARCHAR NOT NULL CHECK (kind IN ('trade', 'commission', 'fee', 'interest', 'dividend', 'deposit', 'withdrawal', 'other')),
    ref        VARCHAR,                          -- fill_id / order_id etc.
    PRIMARY KEY (run_id, entry_id)
);

-- Daily NAV, per sleeve and for the whole portfolio (sleeve = 'total').
CREATE TABLE nav (
    run_id   VARCHAR NOT NULL,
    as_of    DATE    NOT NULL,
    sleeve   VARCHAR NOT NULL CHECK (sleeve IN ('vol', 'equity', 'spread', 'reserve', 'total')),
    nav      DOUBLE  NOT NULL,
    cash     DOUBLE,
    pnl_day  DOUBLE,
    PRIMARY KEY (run_id, as_of, sleeve)
);
