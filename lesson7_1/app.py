import streamlit as st
from crawler import fetch_rates
from ui_helpers import df_from_rates, clean_for_display, filter_tradable, convert_twd
import pandas as pd


st.set_page_config(page_title="台幣匯率轉換", layout="wide")


@st.cache_data(ttl=600)
def get_rates_cached():
    return fetch_rates()


def main():
    st.title("台幣匯率轉換")

    # Manual update button
    cols_top = st.columns([3, 1])
    with cols_top[1]:
        if st.button("手動更新"):
            st.cache_data.clear()

    data = get_rates_cached()
    rates = data.get("rates", [])
    fetched_at = data.get("fetched_at", "")
    error = data.get("error")

    df = df_from_rates(rates)
    df_tradable = filter_tradable(df)
    df_display = clean_for_display(df_tradable)

    col1, col2 = st.columns(2)

    with col1:
        st.header("匯率計算器")
        twd = st.number_input("台幣金額 (TWD)", min_value=0.0, value=1000.0, step=100.0, format="%.2f")

        rate_cols = ["cash_buy", "cash_sell", "spot_buy", "spot_sell"]
        rate_labels = {"cash_buy": "現金買入", "cash_sell": "現金賣出", "spot_buy": "即期買入", "spot_sell": "即期賣出"}
        chosen_label = st.selectbox("使用匯率欄位", [rate_labels[c] for c in rate_cols], index=3)
        inv = {v: k for k, v in rate_labels.items()}
        chosen_col = inv[chosen_label]

        codes = df_display["code"].tolist() if not df_display.empty else []
        if codes:
            chosen_code = st.selectbox("選擇目標貨幣 (代碼)", codes)
            row = df_display[df_display["code"] == chosen_code].iloc[0]
            rate_val = row.get(chosen_col)
            converted = convert_twd(twd, rate_val)
            st.markdown(f"**使用 {rate_labels[chosen_col]}，匯率：`{rate_val}`**")
            if converted is None:
                st.warning("無法使用選定的匯率進行換算（可能為暫停交易）。")
            else:
                st.success(f"{twd:.2f} TWD = {converted:.6f} {chosen_code}")
        else:
            st.info("目前沒有可交易的貨幣資料。")

    with col2:
        st.header("匯率表格")
        if error:
            st.error(f"抓取匯率發生錯誤：{error}")
        st.caption(f"資料時間 (UTC): {fetched_at}")
        if df_display.empty:
            st.info("沒有可顯示的匯率資料。")
        else:
            st.dataframe(df_display[["code", "currency", "cash_buy", "cash_sell", "spot_buy", "spot_sell"]])


if __name__ == "__main__":
    main()
