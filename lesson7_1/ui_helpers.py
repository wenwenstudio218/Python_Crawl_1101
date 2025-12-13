import pandas as pd
from typing import List, Dict, Any, Optional


def df_from_rates(rates: List[Dict[str, Any]]) -> pd.DataFrame:
    if not rates:
        return pd.DataFrame(columns=["currency", "code", "cash_buy", "cash_sell", "spot_buy", "spot_sell", "tradable"])
    df = pd.DataFrame(rates)
    # ensure columns exist
    for c in ["currency", "code", "cash_buy", "cash_sell", "spot_buy", "spot_sell", "tradable"]:
        if c not in df.columns:
            df[c] = None
    return df


def clean_for_display(df: pd.DataFrame) -> pd.DataFrame:
    """將空值轉為「暫停交易」，保留 `code` 與 `currency` 欄位供 UI 選擇。"""
    display = df.copy()
    for col in ["cash_buy", "cash_sell", "spot_buy", "spot_sell"]:
        if col in display.columns:
            display[col] = display[col].fillna("")
            display[col] = display[col].replace("", "暫停交易")
    return display


def filter_tradable(df: pd.DataFrame) -> pd.DataFrame:
    if "tradable" in df.columns:
        return df[df["tradable"] == True].reset_index(drop=True)
    # fallback: consider rows with any numeric rate as tradable
    mask = (df[["cash_buy", "cash_sell", "spot_buy", "spot_sell"]].notna().any(axis=1))
    return df[mask].reset_index(drop=True)


def parse_rate_value(raw: Optional[str]) -> Optional[float]:
    if raw is None:
        return None
    try:
        s = str(raw).replace(",", "").strip()
        return float(s)
    except Exception:
        return None


def convert_twd(twd_amount: float, rate_value: Optional[str]) -> Optional[float]:
    """以牌告匯率將 TWD 轉為外幣：外幣數量 = TWD / rate_value

    若 rate_value 無法解析，回傳 None。
    """
    rv = parse_rate_value(rate_value)
    if rv is None or rv == 0:
        return None
    return twd_amount / rv


if __name__ == "__main__":
    import json
    from crawler import fetch_rates

    data = fetch_rates()
    df = df_from_rates(data.get("rates", []))
    print(df.head().to_json(orient="records", force_ascii=False))
