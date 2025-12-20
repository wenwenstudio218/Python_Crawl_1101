"""lesson8.app

tkinter 桌面應用：台灣銀行牌告匯率查詢與台幣轉換計算器

說明：
- 提供 `fetch_exchange_rates()` 爬取匯率（優先嘗試 crawl4ai，若無則備援 requests+BeautifulSoup）
- GUI 使用 tkinter + ttk，Treeview 顯示匯率並提供下拉選單與轉換計算
"""
from __future__ import annotations

import asyncio
import json
import threading
from datetime import datetime
from typing import Dict, List, Optional

import tkinter as tk
from tkinter import ttk, messagebox

try:
    # 優先使用 crawl4ai（若環境中可用）
    from crawl4ai import AsyncWebCrawler, CrawlerRunConfig, CacheMode  # type: ignore
    from crawl4ai.extraction_strategy import JsonCssExtractionStrategy  # type: ignore
    _HAS_CRAWL4AI = True
except Exception:
    _HAS_CRAWL4AI = False

try:
    import requests
    from bs4 import BeautifulSoup
    _HAS_REQUESTS = True
except Exception:
    _HAS_REQUESTS = False


async def _async_fetch_with_crawl4ai(url: str) -> Optional[List[Dict[str, str]]]:
    """使用 crawl4ai 非同步爬取並解析匯率（若可用）。

    這裡使用簡單 JsonCssExtractionStrategy 範例；若 crawl4ai API 與版本差異導致錯誤，呼叫端會退回同步備援。
    """
    try:
        crawler = AsyncWebCrawler()
        run_config = CrawlerRunConfig(
            urls=[url],
            cache_mode=CacheMode.BYPASS,
        )

        # 範例策略：如果 crawl4ai 的 JsonCssExtractionStrategy 可用，嘗試使用
        strategy = JsonCssExtractionStrategy(
            json_css_extraction=[
                {
                    "table": "table[title='牌告匯率']",
                    "rows": "table[title='牌告匯率'] tbody tr",
                }
            ]
        )

        result = await crawler.run(run_config, extraction_strategy=strategy)
        # 嘗試解析常見結構，輸出 List[Dict]
        data = []
        if isinstance(result, dict):
            # 可能需要依實際回傳格式調整
            for k, v in result.items():
                if isinstance(v, list):
                    for item in v:
                        if isinstance(item, dict):
                            data.append({k2: str(v2).strip() for k2, v2 in item.items()})
        return data or None
    except Exception:
        return None


def _parse_table_html(html: str) -> Optional[List[Dict[str, str]]]:
    """使用 BeautifulSoup 解析 `table[title='牌告匯率']` 並回傳清理後資料。

    每個回傳項目包含至少：'currency', 'buy', 'sell'
    """
    if not _HAS_REQUESTS:
        return None

    soup = BeautifulSoup(html, "html.parser")
    table = soup.find("table", attrs={"title": "牌告匯率"})
    if table is None:
        # 嘗試更寬鬆的匹配
        table = soup.find("table")
        if table is None:
            return None

    # 解析表頭以判定欄位索引
    headers = [th.get_text(strip=True) for th in table.find_all("th")]
    # 常見 header 關鍵字
    buy_keys = ["即期買入", "本行即期買入", "銀行即期買入"]
    sell_keys = ["即期賣出", "本行即期賣出", "銀行即期賣出"]

    def find_index(keys: List[str]) -> Optional[int]:
        for k in keys:
            if k in "|".join(headers):
                for i, h in enumerate(headers):
                    if k in h:
                        return i
        return None

    buy_idx = find_index(buy_keys)
    sell_idx = find_index(sell_keys)

    rows = []
    tbody = table.find("tbody") or table
    for tr in tbody.find_all("tr"):
        tds = tr.find_all(["td", "th"])
        if not tds:
            continue

        text_cells = [td.get_text(strip=True) for td in tds]

        # 幣別通常在第一欄
        currency = text_cells[0] if len(text_cells) >= 1 else ""

        buy = None
        sell = None
        if buy_idx is not None and buy_idx < len(text_cells):
            buy = text_cells[buy_idx]
        elif len(text_cells) >= 2:
            buy = text_cells[1]

        if sell_idx is not None and sell_idx < len(text_cells):
            sell = text_cells[sell_idx]
        elif len(text_cells) >= 3:
            sell = text_cells[2]

        # 清理空白與非數字（保持原字串以便顯示「暫停交易」）
        rows.append({
            "currency": currency,
            "本行即期買入": buy or "",
            "本行即期賣出": sell or "",
        })

    return rows


async def fetch_exchange_rates() -> Optional[List[Dict[str, str]]]:
    """嘗試取得台灣銀行牌告匯率

    策略：
    1. 若可用則優先使用 `crawl4ai` 的非同步爬蟲。
    2. 否則退回到同步的 `requests` + `BeautifulSoup` 解析。

    回傳格式：List[Dict[str,str]] 每個 dict 包含 keys: 'currency', '本行即期買入', '本行即期賣出'
    """
    url = "https://rate.bot.com.tw/xrt?Lang=zh-TW"

    # 優先嘗試 crawl4ai
    if _HAS_CRAWL4AI:
        data = await _async_fetch_with_crawl4ai(url)
        if data:
            # 嘗試標準化欄位名稱
            normalized = []
            for item in data:
                # 找 currency-like 欄位
                currency = item.get("currency") or item.get("幣別") or item.get("Name") or ""
                buy = item.get("本行即期買入") or item.get("即期買入") or item.get("Buy") or ""
                sell = item.get("本行即期賣出") or item.get("即期賣出") or item.get("Sell") or ""
                normalized.append({
                    "currency": str(currency).strip(),
                    "本行即期買入": str(buy).strip(),
                    "本行即期賣出": str(sell).strip(),
                })
            return normalized

    # 備援方案：requests + BeautifulSoup
    if _HAS_REQUESTS:
        try:
            resp = requests.get(url, timeout=15)
            resp.raise_for_status()
            parsed = _parse_table_html(resp.text)
            return parsed
        except Exception:
            return None

    return None


class ExchangeRateApp(tk.Tk):
    """匯率查詢應用程式主視窗（tk.Tk 子類）。"""

    def __init__(self) -> None:
        super().__init__()
        self.title("台灣銀行匯率查詢系統")
        self.geometry("1200x750")

        # 資料
        self.exchange_data: List[Dict[str, str]] = []
        self.last_update: Optional[datetime] = None
        self.is_loading = False

        # UI 元件佈局
        self._setup_ui()

        # 啟動時載入資料
        self._load_initial_data()

    def _setup_ui(self) -> None:
        """建立 UI 元件與佈局。"""
        # 樣式
        style = ttk.Style(self)
        style.theme_use("default")

        # 標題欄
        header = ttk.Frame(self, padding=(10, 12))
        header.grid(row=0, column=0, columnspan=2, sticky="ew")
        header.columnconfigure(0, weight=1)

        title_label = ttk.Label(header, text="🏦 台灣銀行匯率查詢系統", font=(None, 20, "bold"))
        title_label.grid(row=0, column=0, sticky="w")

        self.update_btn = ttk.Button(header, text="🔄 更新匯率", command=self._fetch_data_thread)
        self.update_btn.grid(row=0, column=1, sticky="e")

        self.time_label = ttk.Label(header, text="最後更新: 尚未更新", font=(None, 11))
        self.time_label.grid(row=1, column=0, sticky="w", pady=(6, 0))

        self.status_label = ttk.Label(header, text="", font=(None, 11))
        self.status_label.grid(row=1, column=1, sticky="e", pady=(6, 0))

        # 左側：Treeview 匯率表格
        left_frame = ttk.Frame(self, padding=10)
        left_frame.grid(row=1, column=0, sticky="nsew")
        self.grid_rowconfigure(1, weight=1)
        self.grid_columnconfigure(0, weight=1)

        columns = ("currency", "buy", "sell")
        self.tree = ttk.Treeview(left_frame, columns=columns, show="headings", height=15)
        self.tree.heading("currency", text="幣別")
        self.tree.heading("buy", text="本行即期買入")
        self.tree.heading("sell", text="本行即期賣出")
        self.tree.column("currency", width=200, anchor="w")
        self.tree.column("buy", width=160, anchor="center")
        self.tree.column("sell", width=160, anchor="center")
        self.tree.grid(row=0, column=0, sticky="nsew")

        vsb = ttk.Scrollbar(left_frame, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=vsb.set)
        vsb.grid(row=0, column=1, sticky="ns")

        # 右側：轉換計算器
        right_frame = ttk.Frame(self, padding=10)
        right_frame.grid(row=1, column=1, sticky="nsew")
        self.grid_columnconfigure(1, weight=0)

        ttk.Label(right_frame, text="💱 台幣轉換計算器", font=(None, 16, "bold")).grid(row=0, column=0, sticky="w")

        ttk.Label(right_frame, text="台幣金額:", font=(None, 14)).grid(row=1, column=0, sticky="w", pady=(12, 4))
        self.twd_entry = ttk.Entry(right_frame, font=(None, 14))
        self.twd_entry.grid(row=2, column=0, sticky="ew")

        ttk.Label(right_frame, text="選擇貨幣:", font=(None, 14)).grid(row=3, column=0, sticky="w", pady=(12, 4))
        self.currency_combo = ttk.Combobox(right_frame, state="readonly", font=(None, 14))
        self.currency_combo.grid(row=4, column=0, sticky="ew")

        self.calc_btn = ttk.Button(right_frame, text="計算", command=self._calculate_conversion)
        self.calc_btn.grid(row=5, column=0, pady=(14, 6), sticky="ew")

        ttk.Label(right_frame, text="結果:", font=(None, 14)).grid(row=6, column=0, sticky="w", pady=(12, 4))
        self.result_text = tk.Text(right_frame, height=12, font=(None, 12), wrap="word")
        self.result_text.grid(row=7, column=0, sticky="nsew")

        right_frame.rowconfigure(7, weight=1)

    def _load_initial_data(self) -> None:
        """程式啟動時載入一次資料（背景執行）。"""
        # 使用背景執行緒以免卡住 UI
        self._fetch_data_thread()

    def _fetch_data_thread(self) -> None:
        """在背景執行緒中抓取匯率資料，完成後更新 UI。"""
        if self.is_loading:
            return

        self.is_loading = True
        self._show_loading()

        def run_fetch():
            try:
                # 如果 fetch_exchange_rates 是 coroutine，必須在新的事件迴圈執行
                if asyncio.iscoroutinefunction(fetch_exchange_rates):
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
                    try:
                        data = loop.run_until_complete(fetch_exchange_rates())
                    finally:
                        loop.close()
                else:
                    # 如果是普通函數（可用於備援情況），直接呼叫
                    data = fetch_exchange_rates()

                # 在主執行緒更新 UI
                self.after(0, lambda: self._update_ui_with_data(data))
            except Exception as e:
                self.after(0, lambda: messagebox.showerror("錯誤", f"抓取匯率失敗: {e}"))
            finally:
                self.is_loading = False

        thread = threading.Thread(target=run_fetch, daemon=True)
        thread.start()

    def _show_loading(self) -> None:
        self.status_label.config(text="⏳ 載入中...", foreground="#3498db")
        self.update_btn.config(state="disabled")
        self.calc_btn.config(state="disabled")

    def _hide_loading(self) -> None:
        self.status_label.config(text="")
        self.update_btn.config(state="normal")
        self.calc_btn.config(state="normal")

    def _update_ui_with_data(self, data: Optional[List[Dict[str, str]]]) -> None:
        """將爬到的資料填入 Treeview 與下拉選單。

        data 預期為 List[Dict]，若為 None 顯示錯誤訊息。
        """
        self._hide_loading()

        if not data:
            messagebox.showerror("錯誤", "無法取得匯率資料。請稍後再試。")
            return

        # 清理並存入 internal state
        cleaned = []
        for item in data:
            currency = item.get("currency") or item.get("幣別") or item.get("Currency") or ""
            buy = item.get("本行即期買入") or item.get("即期買入") or ""
            sell = item.get("本行即期賣出") or item.get("即期賣出") or ""

            cleaned.append({
                "currency": str(currency).strip(),
                "本行即期買入": str(buy).strip(),
                "本行即期賣出": str(sell).strip(),
            })

        self.exchange_data = cleaned
        self.last_update = datetime.now()

        # 更新 Treeview
        for i in self.tree.get_children():
            self.tree.delete(i)

        for row in self.exchange_data:
            buy = row.get("本行即期買入") or "暫停交易"
            sell = row.get("本行即期賣出") or "暫停交易"
            self.tree.insert("", "end", values=(row.get("currency", ""), buy, sell))

        # 更新下拉選單（僅包含可交易貨幣）
        available = []
        for r in self.exchange_data:
            c = r.get("currency", "")
            b = r.get("本行即期買入", "").strip()
            s = r.get("本行即期賣出", "").strip()
            if c and b and s and b != "暫停交易" and s != "暫停交易":
                try:
                    # 驗證是否為數值
                    float(b.replace(',', ''))
                    float(s.replace(',', ''))
                    available.append(c)
                except Exception:
                    continue

        self.currency_combo["values"] = available
        if available:
            self.currency_combo.current(0)

        # 更新時間與狀態
        self.time_label.config(text=f"最後更新: {self.last_update.strftime('%Y-%m-%d %H:%M:%S')}")
        self.status_label.config(text="✅ 更新成功", foreground="#27ae60")
        self.after(3000, lambda: self.status_label.config(text=""))

    def _find_rate_by_currency(self, currency: str) -> Optional[Dict[str, str]]:
        for r in self.exchange_data:
            if r.get("currency") == currency:
                return r
        return None

    def _calculate_conversion(self) -> None:
        """計算台幣轉換成外幣的結果並顯示。

        使用：
        - 買入匯率 -> 銀行買入外幣 (您賣台幣，可得外幣)
        - 賣出匯率 -> 銀行賣出外幣 (您買外幣，需付台幣)
        """
        try:
            twd_text = self.twd_entry.get().strip()
            if not twd_text:
                messagebox.showwarning("警告", "請輸入台幣金額")
                return

            # 允許千分符
            twd_amount = float(twd_text.replace(',', ''))
            if twd_amount <= 0:
                messagebox.showwarning("警告", "金額必須大於 0")
                return

            cur = self.currency_combo.get()
            if not cur:
                messagebox.showwarning("警告", "請選擇目標貨幣")
                return

            rate_data = self._find_rate_by_currency(cur)
            if not rate_data:
                messagebox.showerror("錯誤", "找不到該幣別的匯率")
                return

            buy_rate_s = rate_data.get("本行即期買入", "").replace(',', '')
            sell_rate_s = rate_data.get("本行即期賣出", "").replace(',', '')
            buy_rate = float(buy_rate_s)
            sell_rate = float(sell_rate_s)

            # 計算：台幣 / 匯率 = 可獲得外幣數量
            buy_result = twd_amount / buy_rate if buy_rate else 0.0
            sell_result = twd_amount / sell_rate if sell_rate else 0.0

            now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            out = (
                f"═══════════════════════════\n"
                f"💰 轉換金額: {twd_amount:,.2f} 台幣\n"
                f"🌍 目標貨幣: {cur}\n"
                f"═══════════════════════════\n\n"
                f"📤 您賣台幣給銀行 (買入匯率)\n"
                f"   匯率: {buy_rate}\n"
                f"   可得: {buy_result:,.4f} {cur}\n\n"
                f"📥 您向銀行買外幣 (賣出匯率)\n"
                f"   匯率: {sell_rate}\n"
                f"   可得: {sell_result:,.4f} {cur}\n\n"
                f"═══════════════════════════\n"
                f"計算時間: {now}\n"
            )

            self.result_text.delete("1.0", tk.END)
            self.result_text.insert(tk.END, out)

        except ValueError:
            messagebox.showerror("錯誤", "請輸入有效的數字金額")
        except Exception as e:
            messagebox.showerror("錯誤", f"計算失敗: {e}")


def main() -> None:
    app = ExchangeRateApp()
    app.mainloop()


if __name__ == "__main__":
    main()
