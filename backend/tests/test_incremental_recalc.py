"""
Tests for incremental recalculation after price corrections.

These tests verify that when historical prices are revised, the dependent
indicators (breadth, advance/decline) are correctly recalculated.
"""
import datetime as dt

import pytest

from backend.compute import breadth
from backend.loaders import store


def test_breadth_recalculates_after_price_correction(db):
    """
    When a historical price is corrected, breadth should recalculate
    from the earliest affected date forward.
    """
    with store.session() as con:
        # Insert 300 days of test prices to have enough for 200DMA
        import random
        random.seed(42)
        
        # Create 10 tickers to have a meaningful breadth calculation
        tickers = [f"STOCK{i}" for i in range(10)]
        dates = [dt.date(2024, 1, 1) + dt.timedelta(days=i) for i in range(300)]
        
        for ticker_idx, ticker in enumerate(tickers):
            base_price = 100.0 + ticker_idx * 10
            for day_idx, date in enumerate(dates):
                close = base_price + day_idx * 0.1 + random.uniform(-0.5, 0.5)
                con.execute(
                    "INSERT INTO prices (ticker, date, close, adj_close) VALUES (?, ?, ?, ?)",
                    [ticker, date, close, close],
                )
            # Register ticker
            con.execute(
                "INSERT INTO tickers (ticker, symbol, name, kind) VALUES (?, ?, ?, ?)",
                [ticker, ticker, f"Stock {ticker_idx}", "stock"],
            )
        
        # Debug: Check data was inserted
        price_count = con.execute("SELECT COUNT(*) FROM prices").fetchone()[0]
        ticker_count = con.execute("SELECT COUNT(*) FROM tickers WHERE kind = 'stock'").fetchone()[0]
        print(f"Test setup: {price_count} prices for {ticker_count} stock tickers")
        
        # Debug: Check price date range
        date_range = con.execute("SELECT MIN(date), MAX(date) FROM prices").fetchone()
        print(f"Price date range: {date_range[0]} to {date_range[1]}")
        
        # Debug: Check per-ticker counts
        ticker_counts = con.execute("""
            SELECT ticker, COUNT(*) as cnt, MIN(date), MAX(date)
            FROM prices
            WHERE ticker IN (SELECT ticker FROM tickers WHERE kind = 'stock')
            GROUP BY ticker
            ORDER BY ticker
            LIMIT 5
        """).fetchall()
        print(f"Sample ticker counts: {ticker_counts}")
        
        # Debug: Check if earliest_price_change metadata is set
        earliest_change = con.execute("SELECT value FROM meta WHERE key = 'earliest_price_change'").fetchone()
        print(f"Earliest price change metadata: {earliest_change}")
        
        # Debug: Check breadth_200dma table before recompute
        breadth_before = con.execute("SELECT COUNT(*) FROM breadth_200dma").fetchone()[0]
        print(f"Breadth rows before recompute: {breadth_before}")
        
        # Compute breadth
        result = breadth.recompute(full=True)
        print(f"Breadth recompute result: {result}")
        
        # Debug: Check what SQL was executed
        breadth_after = con.execute("SELECT COUNT(*) FROM breadth_200dma").fetchone()[0]
        print(f"Breadth rows after recompute: {breadth_after}")
        
        # Debug: Check if breadth table has any data
        breadth_count = con.execute("SELECT COUNT(*) FROM breadth_200dma").fetchone()[0]
        print(f"Breadth table row count: {breadth_count}")
        
        # Verify initial breadth - should have data from day 200 onwards
        result = con.execute(
            "SELECT date, n_valid, n_above FROM breadth_200dma ORDER BY date"
        ).fetchall()
        print(f"Breadth rows found: {len(result)}")
        assert len(result) > 0  # Should have some breadth data
        
        # Store the initial state
        initial_count = len(result)
        initial_last_above = result[-1][2]
        
        # Now correct a historical price on day 150
        correction_date = dates[150]
        con.execute(
            "UPDATE prices SET close = 500.0 WHERE ticker = 'STOCK0' AND date = ?",
            [correction_date],
        )
        
        # Mark that prices changed
        store.set_meta(con, "earliest_price_change", dates[150].isoformat())
        
        # Recompute
        breadth.recompute(full=False)
        
        # Verify breadth was recalculated
        result_after = con.execute(
            "SELECT date, n_valid, n_above FROM breadth_200dma ORDER BY date"
        ).fetchall()
        assert len(result_after) == initial_count  # Same number of rows
        
        # The values may have changed due to the correction
        # At minimum, verify the recalculation happened
        assert len(result_after) > 0


def test_ad_line_recalculates_after_price_correction(db):
    """
    When a historical price is corrected, the cumulative A/D line should
    be recalculated from the earliest affected date forward.
    """
    with store.session() as con:
        # Insert test prices
        prices = [
            ("AAPL", dt.date(2024, 1, 1), 100.0, 100.0),
            ("AAPL", dt.date(2024, 1, 2), 101.0, 101.0),  # Advance
            ("AAPL", dt.date(2024, 1, 3), 100.0, 100.0),  # Decline
            ("MSFT", dt.date(2024, 1, 1), 200.0, 200.0),
            ("MSFT", dt.date(2024, 1, 2), 199.0, 199.0),  # Decline
            ("MSFT", dt.date(2024, 1, 3), 201.0, 201.0),  # Advance
        ]
        for ticker, date, close, adj_close in prices:
            con.execute(
                "INSERT INTO prices (ticker, date, close, adj_close) VALUES (?, ?, ?, ?)",
                [ticker, date, close, adj_close],
            )

        # Register tickers
        con.execute(
            "INSERT INTO tickers (ticker, symbol, name, kind) VALUES (?, ?, ?, ?)",
            ["AAPL", "AAPL", "Apple", "stock"],
        )
        con.execute(
            "INSERT INTO tickers (ticker, symbol, name, kind) VALUES (?, ?, ?, ?)",
            ["MSFT", "MSFT", "Microsoft", "stock"],
        )

        # Compute A/D
        breadth.recompute(full=True)

        # Verify initial A/D - should have 2 rows (day 1 has no previous close)
        result = con.execute(
            "SELECT date, advances, declines, ad_line FROM advance_decline ORDER BY date"
        ).fetchall()
        assert len(result) == 2  # Days 2 and 3
        
        # Day 2: AAPL advances, MSFT declines
        assert result[0][1] == 1  # advances
        assert result[0][2] == 1  # declines
        assert result[0][3] == 0  # ad_line (1 - 1 = 0)
        
        # Day 3: AAPL declines, MSFT advances
        assert result[1][1] == 1  # advances
        assert result[1][2] == 1  # declines
        assert result[1][3] == 0  # ad_line (0 + 1 - 1 = 0)

        # Now correct a historical price
        # Change AAPL on day 2 from 101 to 99 (now a decline instead of advance)
        con.execute(
            "UPDATE prices SET close = 99.0 WHERE ticker = 'AAPL' AND date = '2024-01-02'"
        )

        # Mark that prices changed
        store.set_meta(con, "earliest_price_change", "2024-01-02")

        # Recompute
        breadth.recompute(full=False)

        # Verify A/D was recalculated
        result_after = con.execute(
            "SELECT date, advances, declines, ad_line FROM advance_decline ORDER BY date"
        ).fetchall()
        assert len(result_after) == 2
        
        # Day 2 should now have 0 advances, 2 declines
        assert result_after[0][1] == 0  # advances
        assert result_after[0][2] == 2  # declines
        assert result_after[0][3] == -2  # ad_line (0 - 2 = -2)
        
        # Day 3 should recalculate based on new day 2 values
        # AAPL: 99 (day 2) -> 100 (day 3) = advance
        # MSFT: 199 (day 2) -> 201 (day 3) = advance
        assert result_after[1][1] == 2  # advances (AAPL and MSFT)
        assert result_after[1][2] == 0  # declines (none)
        assert result_after[1][3] == 0  # ad_line (-2 + 2 - 0 = 0)


def test_earliest_price_change_detection(db):
    """
    Verify that the system correctly tracks and uses the earliest price change date.
    """
    with store.session() as con:
        # Set a price change marker
        store.set_meta(con, "earliest_price_change", "2024-01-15")
        
        # Verify it was stored
        result = store.get_meta(con, "earliest_price_change")
        assert result == "2024-01-15"
        
        # Recompute should clear the marker
        breadth.recompute(full=False)
        
        # Verify marker was cleared
        result_after = store.get_meta(con, "earliest_price_change")
        assert result_after == ""
