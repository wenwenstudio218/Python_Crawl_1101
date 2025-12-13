# lesson7_1 — 台幣匯率轉換 (Streamlit 應用)

功能摘要
- 使用 `crawl4ai`（若可用）或 `requests` + `BeautifulSoup` 抓取 BOT (https://rate.bot.com.tw/xrt?Lang=zh-TW) 的牌告匯率。
- 使用 `streamlit` 顯示兩欄介面：左側匯率計算器、右側匯率表格。
- 自動快取 10 分鐘（`st.cache_data(ttl=600)`），同時提供手動更新按鈕。
- 欄位若無數值顯示為 `暫停交易`；不可交易的貨幣不會顯示在表格與匯率下拉中。

啟動

1. 建議建立虛擬環境並安裝需求：

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r lesson7_1/requirements.txt
```

2. 本地啟動 Streamlit 應用：

```bash
streamlit run lesson7_1/app.py
```

注意事項
- 專案會優先使用 `crawl4ai`（若已安裝並可使用），若 crawl4ai 無法使用會自動改為 requests + BeautifulSoup。
- 若需背景長時間定時抓取（非使用者瀏覽時更新），建議改用 `APScheduler` 或外部雲端排程。文中僅以 `st.cache_data(ttl=600)` 作為 10 分鐘自動更新策略。
