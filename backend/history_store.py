"""PostgreSQL-backed persistent storage for read-only signal history."""

import json
import os
from datetime import datetime

import psycopg
from psycopg.types.json import Jsonb


TABLE_NAME = "forex_signal_history"


def _database_url():
    url = os.environ.get("DATABASE_URL", "").strip()
    if not url:
        raise RuntimeError("DATABASE_URL is not configured")
    return url


def initialize_history_store():
    """Create the signal-history table if it does not already exist."""
    with psycopg.connect(_database_url(), connect_timeout=10) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS forex_signal_history (
                id BIGSERIAL PRIMARY KEY,
                logged_at TIMESTAMPTZ NOT NULL,
                symbol TEXT NOT NULL,
                timeframe TEXT NOT NULL,
                candle_time TEXT NOT NULL,
                candle_id TEXT NOT NULL,
                signal TEXT NOT NULL,
                details JSONB NOT NULL,
                trading_enabled BOOLEAN NOT NULL DEFAULT FALSE,
                order_submitted BOOLEAN NOT NULL DEFAULT FALSE,
                record JSONB NOT NULL,
                UNIQUE (symbol, timeframe, candle_id)
            )
            """
        )
        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS
            forex_signal_history_latest_idx
            ON forex_signal_history
            (symbol, timeframe, logged_at DESC)
            """
        )


def load_last_processed_candle(symbol, timeframe):
    """Return the most recently stored candle identity, if one exists."""
    with psycopg.connect(_database_url(), connect_timeout=10) as conn:
        row = conn.execute(
            """
            SELECT candle_id
            FROM forex_signal_history
            WHERE symbol = %s AND timeframe = %s
            ORDER BY logged_at DESC, id DESC
            LIMIT 1
            """,
            (symbol, timeframe),
        ).fetchone()

    return row[0] if row else None


def append_database_record(record, max_entries=5000):
    """
    Persist one signal atomically.

    Returns True if inserted, or False if that candle was already stored.
    """
    clean_record = json.loads(json.dumps(record, default=str))
    logged_at = datetime.fromisoformat(
        clean_record["logged_at"].replace("Z", "+00:00")
    )

    with psycopg.connect(_database_url(), connect_timeout=10) as conn:
        inserted = conn.execute(
            """
            INSERT INTO forex_signal_history (
                logged_at, symbol, timeframe, candle_time, candle_id,
                signal, details, trading_enabled, order_submitted, record
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (symbol, timeframe, candle_id) DO NOTHING
            RETURNING id
            """,
            (
                logged_at,
                clean_record["symbol"],
                clean_record["timeframe"],
                str(clean_record["candle_time"]),
                clean_record["candle_id"],
                clean_record["signal"],
                Jsonb(clean_record.get("details", {})),
                bool(clean_record.get("trading_enabled", False)),
                bool(clean_record.get("order_submitted", False)),
                Jsonb(clean_record),
            ),
        ).fetchone()

        if inserted and max_entries > 0:
            conn.execute(
                """
                WITH ranked AS (
                    SELECT id,
                           ROW_NUMBER() OVER (
                               PARTITION BY symbol, timeframe
                               ORDER BY logged_at DESC, id DESC
                           ) AS row_number
                    FROM forex_signal_history
                    WHERE symbol = %s AND timeframe = %s
                )
                DELETE FROM forex_signal_history
                WHERE id IN (
                    SELECT id FROM ranked WHERE row_number > %s
                )
                """,
                (
                    clean_record["symbol"],
                    clean_record["timeframe"],
                    max_entries,
                ),
            )

    return inserted is not None
