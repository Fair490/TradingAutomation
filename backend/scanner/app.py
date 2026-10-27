"""
Streamlit Frontend for NSE Stock Scanner
"""

import streamlit as st
import pandas as pd
import os
from datetime import datetime
from pathlib import Path
import sys

# Add parent directory to path to import scanner
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from backend.scanner.scanner_v2 import run_scanner, OUTPUT_DIR

# Page config
st.set_page_config(
    page_title="NSE Stock Scanner",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS
st.markdown("""
<style>
    .main-header {
        font-size: 2.5rem;
        font-weight: bold;
        color: #1f77b4;
        margin-bottom: 1rem;
    }
    .metric-card {
        background-color: #f0f2f6;
        border-radius: 10px;
        padding: 1rem;
        text-align: center;
    }
    .stButton>button {
        width: 100%;
        background-color: #1f77b4;
        color: white;
        font-weight: bold;
    }
</style>
""", unsafe_allow_html=True)


def get_latest_results() -> pd.DataFrame:
    """Get the latest scan results from output directory."""
    output_dir = Path(OUTPUT_DIR)
    if not output_dir.exists():
        return pd.DataFrame()
    
    # Find latest Excel file
    excel_files = list(output_dir.glob("scan_results_*.xlsx"))
    if not excel_files:
        return pd.DataFrame()
    
    latest_file = max(excel_files, key=os.path.getmtime)
    
    try:
        df = pd.read_excel(latest_file)
        return df
    except Exception as e:
        st.error(f"Error loading results: {e}")
        return pd.DataFrame()


def main():
    # Header
    st.markdown('<div class="main-header">📊 NSE Stock Scanner</div>', unsafe_allow_html=True)
    st.markdown("Technical analysis-based stock screener for Indian equities")
    
    # Sidebar
    with st.sidebar:
        st.header("⚙️ Scanner Controls")
        
        # Run scan button
        if st.button("🔄 Run New Scan", type="primary"):
            with st.spinner("Running scan... This may take 5-15 minutes..."):
                try:
                    results = run_scanner()
                    st.success(f"Scan complete! {len(results)} stocks found.")
                    st.rerun()
                except Exception as e:
                    st.error(f"Scan failed: {e}")
        
        st.markdown("---")
        
        # Filters
        st.header("🔍 Filters")
        
        # Load results
        df = get_latest_results()
        
        if not df.empty:
            # RS Percentile filter
            min_percentile = int(df['RS_Percentile'].min())
            max_percentile = int(df['RS_Percentile'].max())
            
            percentile_range = st.slider(
                "RS Percentile Range",
                min_value=min_percentile,
                max_value=max_percentile,
                value=(min_percentile, max_percentile)
            )
            
            # Close price filter
            min_close = float(df['Close'].min())
            max_close = float(df['Close'].max())
            
            close_range = st.slider(
                "Close Price Range (₹)",
                min_value=min_close,
                max_value=max_close,
                value=(min_close, max_close),
                format="%.2f"
            )
            
            # Top N display
            top_n = st.slider("Display Top N Stocks", 10, 100, 25, 5)
    
    # Main content
    if df.empty:
        st.warning("No scan results found. Click 'Run New Scan' to start.")
        return
    
    # Apply filters
    filtered_df = df[
        (df['RS_Percentile'] >= percentile_range[0]) &
        (df['RS_Percentile'] <= percentile_range[1]) &
        (df['Close'] >= close_range[0]) &
        (df['Close'] <= close_range[1])
    ]
    
    # Metrics
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.metric("Total Stocks", len(df))
    
    with col2:
        st.metric("Filtered Stocks", len(filtered_df))
    
    with col3:
        avg_rs_score = filtered_df['RS_Score_Pct'].mean()
        st.metric("Avg RS Score", f"{avg_rs_score:.2f}%")
    
    with col4:
        avg_pct_below_high = filtered_df['Pct_Below_52W_High'].mean()
        st.metric("Avg % Below 52W High", f"{avg_pct_below_high:.2f}%")
    
    st.markdown("---")
    
    # Results table
    st.subheader(f"📈 Scan Results (Top {min(top_n, len(filtered_df))})")
    
    # Format for display
    display_df = filtered_df.head(top_n).copy()
    
    # Create formatted columns
    formatted_df = pd.DataFrame({
        'Rank': display_df['Rank'],
        'Symbol': display_df['Symbol'],
        'Close': display_df['Close'].map(lambda x: f"₹{x:.2f}"),
        'EMA50': display_df['EMA50'].map(lambda x: f"₹{x:.2f}"),
        'EMA150': display_df['EMA150'].map(lambda x: f"₹{x:.2f}"),
        '52W High': display_df['52W_High'].map(lambda x: f"₹{x:.2f}"),
        '% Below 52W': display_df['Pct_Below_52W_High'].map(lambda x: f"{x:.2f}%"),
        '% vs EMA50': display_df['Close_vs_EMA50_Pct'].map(lambda x: f"{x:.2f}%"),
        'RS Ratio': display_df['RS_Ratio'].map(lambda x: f"{x:.4f}"),
        'RS Score': display_df['RS_Score_Pct'].map(lambda x: f"{x:.2f}%"),
        'RS %ile': display_df['RS_Percentile']
    })
    
    st.dataframe(
        formatted_df,
        use_container_width=True,
        height=600
    )
    
    # Export options
    st.markdown("---")
    col1, col2 = st.columns(2)
    
    with col1:
        # CSV download
        csv = filtered_df.to_csv(index=False)
        st.download_button(
            label="📥 Download CSV",
            data=csv,
            file_name=f"scanner_results_{datetime.now().strftime('%Y-%m-%d')}.csv",
            mime="text/csv"
        )
    
    with col2:
        # Excel download
        excel_buffer = pd.ExcelWriter('/tmp/scanner_results.xlsx', engine='xlsxwriter')
        filtered_df.to_excel(excel_buffer, index=False, sheet_name='Results')
        excel_buffer.close()
        
        with open('/tmp/scanner_results.xlsx', 'rb') as f:
            excel_data = f.read()
        
        st.download_button(
            label="📥 Download Excel",
            data=excel_data,
            file_name=f"scanner_results_{datetime.now().strftime('%Y-%m-%d')}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
    
    # Info section
    with st.expander("ℹ️ About the Scanner"):
        st.markdown("""
        ### Scan Criteria (All Must Be True)
        
        1. **Close >= EMA50**: Stock is above its 50-day EMA
        2. **Close >= 0.70 × 52W High**: Stock is within 30% of its 52-week high
        3. **EMA50 >= EMA150**: 50-day EMA is above 150-day EMA (uptrend)
        
        ### Ranking
        
        Stocks are ranked by **RS Score** (Relative Strength score), which measures
        the stock's performance vs Nifty 500 over the last 126 trading days.
        
        **RS Percentile** shows where the stock ranks compared to the entire universe
        (1-99, where 99 is the top 1%).
        
        ### Configuration
        
        All parameters can be adjusted in `backend/scanner/scanner_v2.py`:
        - EMA periods (50, 150)
        - 52-week high threshold (70%)
        - RS lookback period (126 days)
        - And more...
        
        See README_SCANNER.md for detailed documentation.
        """)


if __name__ == "__main__":
    main()
