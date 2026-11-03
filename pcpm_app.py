import time

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

# ==========================================
# 1. CẤU HÌNH
# ==========================================
st.set_page_config(page_title="SHB - Dòng tiền lớn/nhỏ", layout="centered",
                   initial_sidebar_state="collapsed")
st.title("📊 SHB - Dòng tiền lệnh lớn vs nhỏ lẻ")

SYMBOL = "SHB"
# (tên khung, phút bắt đầu, phút kết thúc) tính từ 00:00
SLOTS = [
    ("ATO 9:00-9:15", 9 * 60, 9 * 60 + 15),
    ("9:15-10:00", 9 * 60 + 15, 10 * 60),
    ("10:00-11:30", 10 * 60, 11 * 60 + 30),
    ("13:00-14:00", 13 * 60, 14 * 60),
    ("14:00-14:30", 14 * 60, 14 * 60 + 30),
    ("ATC 14:30-14:45", 14 * 60 + 30, 14 * 60 + 45),
]

use_real = st.sidebar.toggle("Dùng dữ liệu thật (vnstock)", value=True)
auto_refresh = st.sidebar.toggle("Tự động làm mới", value=False)
refresh_interval = st.sidebar.slider("Chu kỳ làm mới (giây)", 5, 60, 15)
st.sidebar.markdown("---")
st.sidebar.markdown("### Cách tách lệnh lớn / nhỏ")
pct = st.sidebar.slider("Lệnh lớn = nằm trong top x% giá trị của phiên", 80, 99, 95)
floor_ty = st.sidebar.slider("Nhưng không nhỏ hơn (tỷ đồng/lệnh)", 0.1, 5.0, 0.5, 0.1)
min_abs = st.sidebar.slider("Bỏ qua dòng tiền ròng nhỏ hơn (tỷ)", 0.0, 2.0, 0.2, 0.05)


# ==========================================
# 2. NGUỒN DỮ LIỆU (trả về bảng các lệnh khớp)
#    cột: time, price, volume, side ('B' mua chủ động / 'S' bán chủ động)
# ==========================================
@st.cache_data(ttl=10, show_spinner=False)
def fetch_trades_vnstock(symbol: str) -> pd.DataFrame:
    from vnstock import Quote  # pip install -U vnstock

    q = Quote(symbol=symbol, source="VCI")
    try:
        raw = q.intraday(page_size=10000)
    except TypeError:
        raw = q.intraday()
    if raw is None or len(raw) == 0:
        raise RuntimeError("Nguồn không trả về lệnh khớp nào (ngoài giờ giao dịch?).")

    df = raw.copy()
    df.columns = [str(c).lower() for c in df.columns]
    tcol = next((c for c in ("time", "datetime", "t") if c in df.columns), None)
    pcol = next((c for c in ("price", "match_price", "p") if c in df.columns), None)
    vcol = next((c for c in ("volume", "match_vol", "vol") if c in df.columns), None)
    if not (tcol and pcol and vcol):
        raise RuntimeError(f"Không nhận diện được cột. Các cột nhận được: {list(df.columns)}")

    out = pd.DataFrame({
        "time": pd.to_datetime(df[tcol]),
        "price": pd.to_numeric(df[pcol], errors="coerce"),
        "volume": pd.to_numeric(df[vcol], errors="coerce"),
    })
    if out["time"].dt.tz is not None:
        out["time"] = out["time"].dt.tz_convert("Asia/Ho_Chi_Minh").dt.tz_localize(None)
    if out["price"].median() < 1000:  # nguồn trả giá theo nghìn đồng
        out["price"] = out["price"] * 1000

    side = None
    scol = next((c for c in ("match_type", "side", "a") if c in df.columns), None)
    if scol:
        s = df[scol].astype(str).str.lower()
        side = np.where(s
