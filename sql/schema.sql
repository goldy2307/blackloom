-- Core transactions table
CREATE TABLE IF NOT EXISTS transactions (
    hash            TEXT PRIMARY KEY,
    from_address    TEXT NOT NULL,
    to_address      TEXT NOT NULL,
    value_eth       REAL NOT NULL,
    gas_price_gwei  REAL NOT NULL,
    tx_time         TEXT NOT NULL,
    block_number    INTEGER NOT NULL,
    is_error        INTEGER DEFAULT 0
);

-- Indexes = what gave the "30% query latency reduction" in the resume line.
-- Without these, filtering by address or date scans every row (full table scan).
CREATE INDEX IF NOT EXISTS idx_tx_from ON transactions(from_address);
CREATE INDEX IF NOT EXISTS idx_tx_to ON transactions(to_address);
CREATE INDEX IF NOT EXISTS idx_tx_time ON transactions(tx_time);
CREATE INDEX IF NOT EXISTS idx_tx_block ON transactions(block_number);

-- Example transformation query Power BI would call:
-- daily volume + tx count, using the tx_time index above
CREATE VIEW IF NOT EXISTS daily_summary AS
SELECT
    DATE(tx_time)              AS day,
    COUNT(*)                   AS tx_count,
    SUM(value_eth)             AS total_eth_volume,
    AVG(gas_price_gwei)        AS avg_gas_price_gwei,
    SUM(is_error)              AS failed_tx_count
FROM transactions
GROUP BY DATE(tx_time)
ORDER BY day DESC;
