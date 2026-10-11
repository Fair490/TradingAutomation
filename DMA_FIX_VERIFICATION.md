# DMA/Moving Average Plot Fix - Verification Report

## Root Causes Identified

### 1. SeriesPanel.tsx - Data Merging Bug
**Problem:** The chart rendered `<Line dataKey="ma50" />` and `<Line dataKey="ma150" />` components, but the `rows` dataset passed to the chart only contained `{date, value}` fields. The MA data was computed separately in `maData` but never merged into the chart dataset.

**Fix:** Replaced the separate `rows` and `maData` with a unified `chartData` useMemo that:
- Builds daily data with MAs merged in
- Applies thin/aggregate transformations to the unified dataset
- Ensures MA values align with price points after aggregation

### 2. EtfPanel.tsx - Incorrect MA Calculation Order
**Problem:** MAs were calculated on aggregated (weekly/monthly) data, meaning a "50-DMA" on weekly view was actually a 50-week MA, not a 50-day MA.

**Fix:** Changed the calculation order to:
1. Compute MAs on daily data first (50-DMA = 50 trading days)
2. Then aggregate both price and MA data together
3. This preserves the correct 50-day and 150-day periods regardless of display interval

### 3. GlobalPanel.tsx - Incorrect MA Calculation Order
**Problem:** Same as EtfPanel - MAs were calculated on already-aggregated rebased data, resulting in incorrect MA periods.

**Fix:** Refactored to:
1. Rebase daily data first
2. Compute MAs on daily rebased data
3. Aggregate everything together
4. This ensures 50-DMA and 150-DMA are always 50/150 trading days

### 4. Backend API - MA Length Mismatch (Previously Fixed)
**Problem:** Backend computed MAs on full dataset but returned filtered price points, causing length mismatch.

**Fix:** Already applied in commit `cf63ef3` - MAs are now filtered to match the display range.

## Files Changed

1. **frontend/src/components/SeriesPanel.tsx**
   - Removed separate `buildMaOverlay()` function
   - Added unified `chartData` useMemo that merges MAs into the dataset
   - Removed dead `MAOverlay` component

2. **frontend/src/components/EtfPanel.tsx**
   - Changed MA calculation to happen on daily data before aggregation
   - Added `showMA50` and `showMA150` to dependency array

3. **frontend/src/components/GlobalPanel.tsx**
   - Refactored `GlobalCombinedChart` to compute MAs on daily rebased data
   - Changed aggregation to happen after MA calculation
   - Fixed TypeScript type issues with `any` casts

4. **frontend/src/lib/__tests__/maCalculation.test.ts** (NEW)
   - Added 9 unit tests for MA calculation
   - Tests cover: basic MA computation, missing values, aggregation alignment, edge cases

## Test Results

### Unit Tests (Vitest)
```
✓ computes 50-DMA correctly on daily data
✓ computes 150-DMA correctly on daily data
✓ handles missing values in MA calculation
✓ aggregates daily data with MAs to weekly correctly
✓ preserves date alignment when aggregating with MAs
✓ returns all nulls when window is larger than data
✓ handles empty data array
✓ handles single data point
✓ handles all null values

Test Files: 1 passed (1)
Tests: 9 passed (9)
```

### Backend Tests (pytest)
```
35 passed, 1 warning in 3.89s
```

### API Verification Tests
```
Test 1: Verify MAs are aligned with price data
  ✓ Lengths match (261 points, 261 MA50 values, 261 MA150 values)

Test 2: Verify MAs are calculated on daily data
  ✓ MA50 is correctly calculated on 50-day window
  Expected last MA50: 141.0402
  Actual last MA50: 141.0402

Test 3: Verify different ranges return different MA lengths
  ✓ 3M: 65 points, 65 MA values
  ✓ 6M: 130 points, 130 MA values
  ✓ 1Y: 261 points, 261 MA values
  ✓ 3Y: 783 points, 783 MA values
  ✓ 5Y: 1305 points, 1305 MA values
```

### TypeScript Compilation
```
✓ No errors
```

## How to Verify in the Running Application

1. **Open the application** at the Vite dev server (port 5173)

2. **Navigate to any panel with price charts:**
   - Macro panel (USD/INR, Dollar Index, US 10Y)
   - Commodities panel (Gold, Silver, Brent)
   - Global panel (indices)
   - ETF panel (click any ETF to expand)

3. **Test the MA toggles:**
   - Click "50 MA" toggle → A dashed line should appear
   - Click "150 MA" toggle → Another dashed line should appear
   - Both toggles can be active simultaneously
   - Lines should be clearly visible and distinct from the price line

4. **Test D/W/M aggregation:**
   - Switch between D (Daily), W (Weekly), M (Monthly)
   - The MA lines should remain visible and correctly positioned
   - On Weekly view, you should see fewer data points but the MA should still represent 50/150 trading days
   - On Monthly view, same behavior

5. **Test different time ranges:**
   - Switch between 1M, 3M, 6M, 1Y, 3Y, 5Y ranges
   - On short ranges (1M), the 50-DMA may not be visible (insufficient data)
   - On longer ranges (5Y), both MAs should be clearly visible

6. **Verify MA correctness:**
   - The 50-DMA should smooth out short-term fluctuations
   - The 150-DMA should be smoother than the 50-DMA
   - Both MAs should lag behind the price (as expected for moving averages)

## Mathematical Verification

For a synthetic dataset with values 100, 101, 102, ..., 159:
- 50-DMA at position 49 should be average of values 100-149 = 124.5
- 50-DMA at position 59 should be average of values 110-159 = 134.5

For the real USD/INR data:
- Last 50 prices average: 141.0402
- API returns: 141.0402
- ✓ Correct

## Edge Cases Handled

1. **Insufficient data:** When there are fewer than 50/150 data points, the MA returns `null` values
2. **Missing values:** If any value in the MA window is `null`, the MA returns `null` for that position
3. **Weekend/holiday gaps:** The `aggregate()` function correctly handles non-trading days
4. **Different series lengths:** Each series maintains its own MA calculation independently

## Remaining Limitations

1. **Browser UI verification:** Could not be performed in this environment (headless sandbox)
   - The code changes are verified through unit tests and API tests
   - Visual verification should be done by the user in their browser

2. **Performance:** For very large datasets (5Y daily), the MA calculation is done client-side
   - This is acceptable for the current data sizes
   - If performance becomes an issue, MAs could be pre-computed on the backend

## Conclusion

✅ All identified bugs have been fixed
✅ All tests pass (unit tests, backend tests, API tests)
✅ TypeScript compiles without errors
✅ MAs are now correctly calculated on daily data (50-DMA = 50 trading days)
✅ MAs are correctly aligned with price data after aggregation
✅ Chart datasets now include the MA fields that the `<Line>` components reference

The moving average plot should now work correctly in all panels.
