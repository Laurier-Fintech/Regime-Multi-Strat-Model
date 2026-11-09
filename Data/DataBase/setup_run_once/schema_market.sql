-- =============================================================================
-- market_data.duckdb : schema (ONE-TIME, run by create_databases.py)
--
-- Everything that comes from the outside world. Written ONLY by
-- Data/DataSources/refresh.py. Everyone else opens this file read-only and reads
-- it ONLY through Data/DataBase/access.py.
--
-- Schemas:
--   meta      catalogue of every series + refresh log + schema version
--   raw       exactly as downloaded (never edited, never overwritten)
--   clean     VIEWS on top of raw (no second copy of the data)
--   features  model inputs built from clean data (filled later by features.py)
--
-- The two dates on every market-data row:
--   obs_date  the day the value is ABOUT
--   known_at  the first day we could have KNOWN it (obs_date + publish lag)
-- A correction from a source is added as a NEW row with a later known_at.
-- Reads take the newest version with known_at <= as_of.
-- =============================================================================

CREATE SCHEMA meta;
CREATE SCHEMA raw;
CREATE SCHEMA clean;
CREATE SCHEMA features;

-- -----------------------------------------------------------------------------
-- meta
-- -----------------------------------------------------------------------------

CREATE TABLE meta.schema_version (
    db_name         VARCHAR   NOT NULL,          -- 'market_data'
    schema_version  INTEGER   NOT NULL,
    duckdb_version  VARCHAR   NOT NULL,
    created_at      TIMESTAMP NOT NULL
);

-- One row per series. series_id is OUR name (lowercase); source_code is the
-- provider's code. Callers only ever use series_id, so a source can change
-- without breaking anyone.
CREATE TABLE meta.series (
    series_id         VARCHAR PRIMARY KEY,
    storage           VARCHAR NOT NULL CHECK (storage IN ('series', 'prices')),
                      -- 'series' -> raw.series (one value per day)
                      -- 'prices' -> raw.prices (open/high/low/close/volume bar)
    source            VARCHAR NOT NULL CHECK (source IN ('fred', 'cboe', 'yfinance', 'bloomberg', 'ibkr')),
    source_code       VARCHAR NOT NULL,
    description       VARCHAR NOT NULL,
    units             VARCHAR NOT NULL,
    frequency         VARCHAR NOT NULL DEFAULT 'daily',
    publish_lag_days  INTEGER NOT NULL CHECK (publish_lag_days >= 0),
                      -- business days between obs_date and known_at
    used_by           VARCHAR NOT NULL,          -- regime, sleeve_a, sleeve_b, sleeve_c, reserve
    is_active         BOOLEAN NOT NULL DEFAULT TRUE,  -- refresh.py downloads active series only
    notes             VARCHAR
);

-- Model-input catalogue. Empty for now; features.py will add rows.
CREATE TABLE meta.features (
    feature_id   VARCHAR PRIMARY KEY,
    description  VARCHAR NOT NULL,
    inputs       VARCHAR NOT NULL,               -- series_ids it is built from
    units        VARCHAR NOT NULL,
    notes        VARCHAR
);

-- One row per series per refresh run: what was updated and when.
CREATE TABLE meta.refresh_log (
    refresh_id    VARCHAR   NOT NULL,
    source        VARCHAR   NOT NULL,
    series_id     VARCHAR   NOT NULL,
    started_at    TIMESTAMP NOT NULL,
    finished_at   TIMESTAMP NOT NULL,
    rows_written  BIGINT    NOT NULL,
    status        VARCHAR   NOT NULL CHECK (status IN ('ok', 'error', 'skipped')),
    message       VARCHAR,
    PRIMARY KEY (refresh_id, series_id)
);

-- -----------------------------------------------------------------------------
-- raw : exactly as downloaded
-- -----------------------------------------------------------------------------

-- Single-value series (FRED, CBOE closes, Bloomberg exports). Long format.
CREATE TABLE raw.series (
    series_id   VARCHAR   NOT NULL,
    obs_date    DATE      NOT NULL,
    value       DOUBLE,
    known_at    DATE      NOT NULL,
    fetched_at  TIMESTAMP NOT NULL,             -- when WE downloaded it (records only)
    PRIMARY KEY (series_id, obs_date, known_at),
    CHECK (known_at >= obs_date)
);

-- Daily bars from yfinance, stored as yfinance returns them:
--   open/high/low/close/volume are SPLIT-adjusted as of fetched_at,
--   adj_close is split- AND dividend-adjusted as of fetched_at.
-- Prices are never revised, so refresh only adds NEW dates here.
-- clean.prices undoes the split adjustment (see below).
CREATE TABLE raw.prices (
    series_id   VARCHAR   NOT NULL,
    obs_date    DATE      NOT NULL,
    open        DOUBLE,
    high        DOUBLE,
    low         DOUBLE,
    close       DOUBLE,
    adj_close   DOUBLE,
    volume      DOUBLE,
    known_at    DATE      NOT NULL,
    fetched_at  TIMESTAMP NOT NULL,
    PRIMARY KEY (series_id, obs_date, known_at),
    CHECK (known_at >= obs_date)
);

-- Dividends and splits from yfinance (dividend is split-adjusted as of fetched_at).
-- split_ratio: 2.0 = 2-for-1 split, 0.1 = 1-for-10 reverse split.
CREATE TABLE raw.corporate_actions (
    series_id    VARCHAR   NOT NULL,
    ex_date      DATE      NOT NULL,
    dividend     DOUBLE,
    split_ratio  DOUBLE,
    known_at     DATE      NOT NULL,
    fetched_at   TIMESTAMP NOT NULL,
    PRIMARY KEY (series_id, ex_date, known_at)
);

-- Implied vol by tenor and moneyness (Bloomberg export shape; OptionMetrics
-- surfaces fit too). underlying is a series_id from meta.series.
CREATE TABLE raw.option_iv (
    underlying      VARCHAR   NOT NULL,
    obs_date        DATE      NOT NULL,
    tenor_days      INTEGER   NOT NULL,          -- calendar days to expiry (30, 60, 90, ...)
    moneyness_type  VARCHAR   NOT NULL CHECK (moneyness_type IN ('pct_spot', 'delta')),
    moneyness       DOUBLE    NOT NULL,          -- e.g. 100 = ATM for pct_spot; 25 / 50 for delta
    iv              DOUBLE,                      -- annualised, decimal (0.20 = 20%)
    source          VARCHAR   NOT NULL,
    known_at        DATE      NOT NULL,
    fetched_at      TIMESTAMP NOT NULL,
    PRIMARY KEY (underlying, obs_date, tenor_days, moneyness_type, moneyness, source, known_at)
);

-- Individual option contracts, one row per contract per day (OptionMetrics /
-- IBKR shape). Empty until the historical options source is decided.
CREATE TABLE raw.option_quotes (
    underlying        VARCHAR   NOT NULL,
    obs_date          DATE      NOT NULL,
    expiry            DATE      NOT NULL,
    strike            DOUBLE    NOT NULL,
    call_put          VARCHAR   NOT NULL CHECK (call_put IN ('C', 'P')),
    contract_id       VARCHAR,                   -- provider id (OCC symbol, optionid, conid)
    bid               DOUBLE,
    ask               DOUBLE,
    last              DOUBLE,
    volume            DOUBLE,
    open_interest     DOUBLE,
    iv                DOUBLE,
    delta             DOUBLE,
    gamma             DOUBLE,
    vega              DOUBLE,
    theta             DOUBLE,
    underlying_price  DOUBLE,
    source            VARCHAR   NOT NULL,
    known_at          DATE      NOT NULL,
    fetched_at        TIMESTAMP NOT NULL,
    PRIMARY KEY (underlying, obs_date, expiry, strike, call_put, source, known_at)
);

-- -----------------------------------------------------------------------------
-- features : model inputs (built later by features.py; no scaling / z-scores)
-- -----------------------------------------------------------------------------

CREATE TABLE features.series (
    feature_id   VARCHAR   NOT NULL,
    obs_date     DATE      NOT NULL,
    value        DOUBLE,
    known_at     DATE      NOT NULL,
    computed_at  TIMESTAMP NOT NULL,
    PRIMARY KEY (feature_id, obs_date, known_at),
    CHECK (known_at >= obs_date)
);

-- -----------------------------------------------------------------------------
-- clean : VIEWS over raw. All versions are kept (known_at included) so that
-- access.py can apply the as-of rule. No calendar alignment yet: that comes
-- when Common/calendar.py exists. Gaps are filled at read time (ffill_limit).
-- -----------------------------------------------------------------------------

-- Drops missing and non-finite values.
CREATE VIEW clean.series AS
SELECT series_id, obs_date, value, known_at
FROM raw.series
WHERE value IS NOT NULL AND isfinite(value);

-- Dividends converted back to the amount actually paid per share on the day
-- (undoes splits that happened after ex_date but before we downloaded it).
CREATE VIEW clean.corporate_actions AS
SELECT
    a.series_id,
    a.ex_date,
    a.dividend * coalesce(product(s.split_ratio), 1.0) AS dividend,
    a.split_ratio,
    a.known_at
FROM raw.corporate_actions a
LEFT JOIN raw.corporate_actions s
       ON s.series_id = a.series_id
      AND s.split_ratio > 0
      AND s.ex_date > a.ex_date
      AND s.ex_date <= CAST(a.fetched_at AS DATE)
GROUP BY a.series_id, a.ex_date, a.dividend, a.split_ratio, a.known_at;

-- Prices as they actually traded on the day (split adjustment undone), plus a
-- daily total return computed from those prices and dividends.
--   open/high/low/close : the real traded prices that day (use for levels, strikes)
--   adj_close           : yfinance adjusted close (ratios OK, LEVEL uses the future)
--   total_return        : (close + dividend) x split ratio / previous close - 1  (use for returns)
CREATE VIEW clean.prices AS
WITH f AS (
    SELECT
        p.series_id, p.obs_date, p.open, p.high, p.low, p.close, p.adj_close, p.volume, p.known_at,
        coalesce(product(s.split_ratio), 1.0) AS split_factor
    FROM raw.prices p
    LEFT JOIN raw.corporate_actions s
           ON s.series_id = p.series_id
          AND s.split_ratio > 0
          AND s.ex_date > p.obs_date
          AND s.ex_date <= CAST(p.fetched_at AS DATE)
    GROUP BY p.series_id, p.obs_date, p.open, p.high, p.low, p.close, p.adj_close, p.volume, p.known_at
),
d AS (  -- per ex-date: cash dividend and split ratio (a 2-for-1 doubles your share count)
    SELECT series_id, ex_date,
           sum(CASE WHEN dividend > 0 THEN dividend END) AS dividend,
           product(CASE WHEN split_ratio > 0 THEN split_ratio END) AS split_ratio
    FROM clean.corporate_actions
    GROUP BY series_id, ex_date
)
SELECT
    f.series_id,
    f.obs_date,
    f.open  * f.split_factor AS open,
    f.high  * f.split_factor AS high,
    f.low   * f.split_factor AS low,
    f.close * f.split_factor AS close,
    f.adj_close,
    f.volume / f.split_factor AS volume,
    coalesce(d.dividend, 0.0) AS dividend,
    ((f.close * f.split_factor + coalesce(d.dividend, 0.0)) * coalesce(d.split_ratio, 1.0))
        / lag(f.close * f.split_factor) OVER (PARTITION BY f.series_id ORDER BY f.obs_date, f.known_at)
        - 1 AS total_return,
    f.known_at
FROM f
LEFT JOIN d ON d.series_id = f.series_id AND d.ex_date = f.obs_date
WHERE f.close IS NOT NULL;

CREATE VIEW clean.option_iv AS
SELECT underlying, obs_date, tenor_days, moneyness_type, moneyness, iv, source, known_at
FROM raw.option_iv
WHERE iv IS NOT NULL AND iv > 0;

CREATE VIEW clean.option_quotes AS
SELECT
    underlying, obs_date, expiry, strike, call_put, contract_id,
    bid, ask,
    CASE WHEN bid > 0 AND ask >= bid THEN (bid + ask) / 2 END AS mid,
    last, volume, open_interest, iv, delta, gamma, vega, theta, underlying_price,
    source, known_at
FROM raw.option_quotes;

-- -----------------------------------------------------------------------------
-- The series catalogue. To add a series: add a row here AND run the same
-- INSERT once on your filled database (or ask Armaan to).
-- publish_lag_days: 0 = known at that day's close; 1 = posted next business day.
-- -----------------------------------------------------------------------------

INSERT INTO meta.series
    (series_id, storage, source, source_code, description, units, publish_lag_days, used_by, notes)
VALUES
    -- FRED: posted the next business day -> lag 1
    ('ust_10y',        'series', 'fred', 'DGS10',        '10-year Treasury constant maturity yield',          'percent', 1, 'regime',            NULL),
    ('ust_2y',         'series', 'fred', 'DGS2',         '2-year Treasury constant maturity yield',           'percent', 1, 'regime',            NULL),
    ('tbill_3m',       'series', 'fred', 'DTB3',         '3-month Treasury bill secondary market rate',       'percent (discount basis)', 1, 'regime,reserve', NULL),
    ('baa_10y_spread', 'series', 'fred', 'BAA10Y',       'Moody''s Baa corporate yield minus 10y Treasury',   'percent', 1, 'regime',            'Long-history credit backup for hy_oas'),
    ('hy_oas_fred',    'series', 'fred', 'BAMLH0A0HYM2', 'ICE BofA US High Yield OAS (FRED copy)',            'percent', 1, 'regime',            'FRED only keeps the last 3 years; cross-check only'),
    ('wti_crude',      'series', 'fred', 'DCOILWTICO',   'WTI crude oil spot, Cushing OK',                    'USD per barrel', 1, 'sleeve_c',   NULL),
    ('usdcad',         'series', 'fred', 'DEXCAUS',      'Canadian dollars per US dollar (noon NY rate)',     'CAD per USD', 1, 'sleeve_c',      NULL),

    -- Bloomberg: manual CSV exports. Index closes computed after the US close -> lag 1 to be safe
    ('hy_oas',         'series', 'bloomberg', 'H0A0 Index', 'ICE BofA US High Yield OAS, full history (Bloomberg)', 'basis points', 1, 'regime', 'Main credit measure. Confirm ticker/field on the terminal before exporting'),

    -- CBOE: index closes, known the same day -> lag 0
    ('vix',            'series', 'cboe', 'VIX',   'CBOE Volatility Index (30-day S&P 500)',  'index points', 0, 'regime,sleeve_a', NULL),
    ('vix3m',          'series', 'cboe', 'VIX3M', 'CBOE 3-month Volatility Index',           'index points', 0, 'regime,sleeve_a', NULL),
    ('vix9d',          'series', 'cboe', 'VIX9D', 'CBOE 9-day Volatility Index',             'index points', 0, 'sleeve_a', NULL),
    ('vvix',           'series', 'cboe', 'VVIX',  'CBOE VIX of VIX',                         'index points', 0, 'sleeve_a', NULL),
    ('vxn',            'series', 'cboe', 'VXN',   'CBOE Nasdaq-100 Volatility Index',        'index points', 0, 'sleeve_a,sleeve_b', 'Rough stand-in for TQQQ vol where no option data'),
    ('skew',           'series', 'cboe', 'SKEW',  'CBOE SKEW Index',                         'index points', 0, 'sleeve_a', NULL),
    ('ovx',            'series', 'cboe', 'OVX',   'CBOE Crude Oil Volatility Index',         'index points', 0, 'sleeve_a', NULL),
    ('gvz',            'series', 'cboe', 'GVZ',   'CBOE Gold Volatility Index',              'index points', 0, 'sleeve_a', NULL),

    -- yfinance: daily bars, known at that day's close -> lag 0
    ('spy',            'prices', 'yfinance', 'SPY',   'SPDR S&P 500 ETF',                     'USD', 0, 'regime,sleeve_b', NULL),
    ('qqq',            'prices', 'yfinance', 'QQQ',   'Invesco QQQ (Nasdaq-100) ETF',         'USD', 0, 'sleeve_b', NULL),
    ('tqqq',           'prices', 'yfinance', 'TQQQ',  'ProShares UltraPro QQQ (3x daily)',    'USD', 0, 'sleeve_b', 'Wheel underlying'),
    ('tlt',            'prices', 'yfinance', 'TLT',   'iShares 20+ Year Treasury Bond ETF',   'USD', 0, 'regime', NULL),
    ('ief',            'prices', 'yfinance', 'IEF',   'iShares 7-10 Year Treasury Bond ETF',  'USD', 0, 'regime', NULL),
    ('hyg',            'prices', 'yfinance', 'HYG',   'iShares iBoxx High Yield Corporate Bond ETF', 'USD', 0, 'regime', NULL),
    ('gld',            'prices', 'yfinance', 'GLD',   'SPDR Gold Shares',                     'USD', 0, 'regime,reserve', NULL),
    ('dbc',            'prices', 'yfinance', 'DBC',   'Invesco DB Commodity Index ETF',       'USD', 0, 'regime', NULL),
    ('uup',            'prices', 'yfinance', 'UUP',   'Invesco DB US Dollar Index Bullish',   'USD', 0, 'regime', NULL),
    ('spx',            'prices', 'yfinance', '^GSPC', 'S&P 500 index',                        'index points', 0, 'sleeve_a,sleeve_b,reserve', NULL),
    ('ndx',            'prices', 'yfinance', '^NDX',  'Nasdaq-100 index',                     'index points', 0, 'sleeve_a,sleeve_b', NULL),
    ('move',           'prices', 'yfinance', '^MOVE', 'ICE BofA MOVE Index (Treasury vol)',   'index points', 0, 'sleeve_a', 'Bloomberg is the backup source');
