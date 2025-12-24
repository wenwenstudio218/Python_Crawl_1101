import tkinter as tk
from tkinter import ttk, messagebox
import threading
import queue
import json
import os
import time
import asyncio
from typing import Dict, List, Optional

# --- 1. 檢查並匯入 Matplotlib (圖表功能) ---
try:
    import matplotlib
    # 設定後端為 Agg (適用於 Tkinter 嵌入)
    matplotlib.use('Agg') 
    from matplotlib.figure import Figure
    from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
    HAS_MPL = True
except ImportError:
    HAS_MPL = False
    print("【警告】未安裝 matplotlib，將無法顯示走勢圖。請執行: pip install matplotlib")

# --- 2. 檢查並匯入 Crawl4AI (爬蟲功能) ---
try:
    from crawl4ai import AsyncWebCrawler, CrawlerRunConfig, BrowserConfig, CacheMode
    from crawl4ai.extraction_strategy import JsonCssExtractionStrategy
    CRAWL4AI_AVAILABLE = True
except ImportError:
    CRAWL4AI_AVAILABLE = False
    print("【警告】未安裝 crawl4ai，無法執行爬蟲。請執行: pip install crawl4ai")


# --- 爬蟲邏輯 (源自 lesson8_1_3.py) ---
def get_stock_schema() -> Dict:
    """取得股票資訊的 CSS 提取 Schema"""
    return {
        "name": "StockInfo",
        "baseSelector": "main.main",
        "fields": [
            {"name": "日期時間", "selector": "time.last-time#lastQuoteTime", "type": "text"},
            {"name": "股票號碼", "selector": "span.astock-code[c-model='id']", "type": "text"},
            {"name": "股票名稱", "selector": "h3.astock-name[c-model='name']", "type": "text"},
            {"name": "即時價格", "selector": "div.quotes-info div.deal", "type": "text"},
            {"name": "漲跌", "selector": "div.quotes-info span.chg[c-model='change']", "type": "text"},
            {"name": "漲跌百分比", "selector": "div.quotes-info span.chg-rate[c-model='changeRate']", "type": "text"},
            {"name": "開盤價", "selector": "div.quotes-info #quotesUl span[c-model-dazzle='text:open,class:openUpDn']", "type": "text"},
            {"name": "最高價", "selector": "div.quotes-info #quotesUl span[c-model-dazzle='text:high,class:highUpDn']", "type": "text"},
            {"name": "成交量", "selector": "div.quotes-info #quotesUl span[c-model='volume']", "type": "text"},
            {"name": "最低價", "selector": "div.quotes-info #quotesUl span[c-model-dazzle='text:low,class:lowUpDn']", "type": "text"},
            {"name": "前一日收盤價", "selector": "div.quotes-info #quotesUl span[c-model='previousClose']", "type": "text"}
        ]
    }

async def fetch_stock_info(crawler: AsyncWebCrawler, stock_code: str, base_config: CrawlerRunConfig, semaphore: asyncio.Semaphore) -> Optional[Dict]:
    """抓取單一股票資訊"""
    async with semaphore:
        url = f'https://www.wantgoo.com/stock/{stock_code}/technical-chart'
        try:
            config = CrawlerRunConfig(
                cache_mode=base_config.cache_mode,
                extraction_strategy=base_config.extraction_strategy,
                scan_full_page=base_config.scan_full_page,
                verbose=base_config.verbose,
                # 等待關鍵元素，確保動態內容載入
                wait_for="js:() => document.querySelector('div.quotes-info div.deal') && document.querySelector('span.astock-code[c-model=\"id\"]')",
                wait_for_timeout=15000,
                page_timeout=30000
            )
            result = await crawler.arun(url=url, config=config)
            
            if result.success and result.extracted_content:
                try:
                    data_list = json.loads(result.extracted_content)
                    if data_list:
                        return {"stock_code": stock_code, "data": data_list[0]}
                except json.JSONDecodeError:
                    print(f"解析 JSON 失敗: {stock_code}")
            return None
        except Exception as e:
            print(f"股票 {stock_code} 發生錯誤: {e}")
            return None

async def crawl_stocks_async(codes: List[str], progress_callback=None) -> Dict[str, Dict]:
    """並行爬取多支股票"""
    if not CRAWL4AI_AVAILABLE:
        return {}

    stock_schema = get_stock_schema()
    extraction_strategy = JsonCssExtractionStrategy(schema=stock_schema)
    browser_config = BrowserConfig(headless=True)
    base_config = CrawlerRunConfig(
        cache_mode=CacheMode.BYPASS,
        extraction_strategy=extraction_strategy,
        scan_full_page=True,
        verbose=False
    )
    semaphore = asyncio.Semaphore(3)

    results_map = {}
    async with AsyncWebCrawler(config=browser_config) as crawler:
        tasks = [fetch_stock_info(crawler, code, base_config, semaphore) for code in codes]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        for i, res in enumerate(results):
            if progress_callback:
                progress_callback(i + 1, len(codes))
            if isinstance(res, dict) and res.get("data"):
                results_map[res["stock_code"]] = res["data"]
            elif isinstance(res, Exception):
                print(f"Crawl error: {res}")
                
    return results_map

# --- 應用程式主類別 ---

class StockMonitorApp:
    WATCHLIST_FILE = os.path.join(os.path.dirname(__file__), "watchlist.json")

    def __init__(self, root):
        self.root = root
        self.root.title("股票即時監控系統")
        self.root.geometry("1100x700")

        self.watchset = set()
        self.card_frames = {}
        self.price_history = {} # code -> list of float
        
        self.task_queue = queue.Queue()
        self.result_queue = queue.Queue()
        self.stop_event = threading.Event()

        self._build_ui()
        
        if not HAS_MPL:
            messagebox.showwarning("功能受限", "未檢測到 matplotlib 套件，圖表功能將無法使用。\n請安裝: pip install matplotlib")

        self._load_watchlist()

        self.crawler_thread = threading.Thread(target=self._crawler_worker, daemon=True)
        self.crawler_thread.start()

        self.root.after(100, self._process_queues)
        self.root.protocol("WM_DELETE_WINDOW", self._on_closing)

    def _build_ui(self):
        # 1. 工具列
        toolbar = ttk.Frame(self.root, padding=5)
        toolbar.pack(fill=tk.X)

        self.update_btn = ttk.Button(toolbar, text="🔄 手動更新", command=self._on_manual_update)
        self.update_btn.pack(side=tk.LEFT, padx=5)

        self.auto_var = tk.BooleanVar(value=False)
        self.auto_check = ttk.Checkbutton(toolbar, text="自動更新 (60s)", variable=self.auto_var, command=self._on_toggle_auto)
        self.auto_check.pack(side=tk.LEFT, padx=5)

        self.progress_bar = ttk.Progressbar(toolbar, mode="determinate", length=200)
        self.progress_bar.pack(side=tk.RIGHT, padx=10)
        
        # 2. 面板分割
        paned = ttk.PanedWindow(self.root, orient=tk.HORIZONTAL)
        paned.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        # 3. 左側面板
        left_frame = ttk.LabelFrame(paned, text="股票清單", width=280, padding=5)
        paned.add(left_frame, weight=1)

        search_frame = ttk.Frame(left_frame)
        search_frame.pack(fill=tk.X, pady=5)
        ttk.Label(search_frame, text="搜尋:").pack(side=tk.LEFT)
        self.search_var = tk.StringVar()
        entry = ttk.Entry(search_frame, textvariable=self.search_var)
        entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)
        entry.bind("<KeyRelease>", self._on_search)

        self.stock_listbox = tk.Listbox(left_frame, height=20)
        self.stock_listbox.pack(fill=tk.BOTH, expand=True, pady=5)
        self.stock_listbox.bind('<Double-Button-1>', lambda e: self._on_add_button())

        ttk.Button(left_frame, text="加入觀察清單 ➕", command=self._on_add_button).pack(fill=tk.X, pady=5)

        # 4. 右側面板
        right_frame = ttk.LabelFrame(paned, text="即時監控儀表板", padding=5)
        paned.add(right_frame, weight=4)

        self.canvas = tk.Canvas(right_frame, bg="#f5f5f5") # 給個背景色區分
        self.scrollbar = ttk.Scrollbar(right_frame, orient="vertical", command=self.canvas.yview)
        self.scrollable_frame = ttk.Frame(self.canvas)

        self.scrollable_frame.bind(
            "<Configure>",
            lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all"))
        )
        self.canvas.create_window((0, 0), window=self.scrollable_frame, anchor="nw")
        self.canvas.configure(yscrollcommand=self.scrollbar.set)
        
        self.canvas.pack(side="left", fill="both", expand=True)
        self.scrollbar.pack(side="right", fill="y")
        self.canvas.bind_all("<MouseWheel>", self._on_mousewheel)

        # 5. 狀態列
        self.status_var = tk.StringVar(value="系統就緒")
        ttk.Label(self.root, textvariable=self.status_var, relief=tk.SUNKEN, anchor=tk.W).pack(fill=tk.X, side=tk.BOTTOM)

        self._init_stock_list()

    def _on_mousewheel(self, event):
        self.canvas.yview_scroll(int(-1*(event.delta/120)), "units")

    def _init_stock_list(self):
        self.all_stocks = []
        try:
            import twstock
            if hasattr(twstock, 'codes'):
                for code, data in twstock.codes.items():
                    name = data.name if hasattr(data, 'name') else str(data)
                    self.all_stocks.append((code, name))
        except Exception:
            self.all_stocks = [("2330", "台積電"), ("2317", "鴻海"), ("2454", "聯發科")]
            
        self.all_stocks.sort(key=lambda x: x[0])
        self.stock_name_map = {code: name for code, name in self.all_stocks}
        self._refresh_listbox()

    def _refresh_listbox(self, filter_txt=""):
        self.stock_listbox.delete(0, tk.END)
        ft = filter_txt.strip().lower()
        for code, name in self.all_stocks:
            if not ft or ft in code or ft in name.lower():
                self.stock_listbox.insert(tk.END, f"{code} - {name}")

    def _on_search(self, event):
        self._refresh_listbox(self.search_var.get())

    def _on_add_button(self):
        sel = self.stock_listbox.curselection()
        if not sel: return
        code = self.stock_listbox.get(sel[0]).split(" - ")[0]
        
        if code not in self.watchset:
            self.watchset.add(code)
            self._create_card(code)
            self.status_var.set(f"已加入 {code}")
            self._trigger_update([code])
        else:
            self.status_var.set(f"{code} 已在清單中")

    def _create_card(self, code):
        if code in self.card_frames: return

        frame = ttk.Frame(self.scrollable_frame, relief=tk.RIDGE, borderwidth=1)
        frame.pack(fill=tk.X, padx=5, pady=5)
        frame.columnconfigure(1, weight=1)
        
        name = self.stock_name_map.get(code, code)
        
        # 資訊區
        info_frame = ttk.Frame(frame)
        info_frame.grid(row=0, column=0, columnspan=2, sticky="nsew", padx=10, pady=5)
        
        ttk.Label(info_frame, text=f"{code} {name}", font=("Microsoft JhengHei", 12, "bold")).pack(anchor="w")
        
        price_lbl = ttk.Label(info_frame, text="--", font=("Arial", 18, "bold"))
        price_lbl.pack(anchor="w", pady=(5,0))
        
        change_lbl = ttk.Label(info_frame, text="-- (--%)", font=("Arial", 11))
        change_lbl.pack(anchor="w")
        
        details = ttk.Label(info_frame, text="開: --  高: --  低: --  量: --", font=("Arial", 9), foreground="gray")
        details.pack(anchor="w", pady=(5,0))
        
        time_lbl = ttk.Label(info_frame, text="更新: --", font=("Arial", 8), foreground="gray")
        time_lbl.pack(anchor="w")

        # 圖表區 (關鍵修正)
        chart_area = None
        if HAS_MPL:
            # 建立圖表 Figure
            fig = Figure(figsize=(4, 1.8), dpi=80) # 加大一點尺寸
            # 設定背景色與 UI 一致或透明
            fig.patch.set_alpha(0.0) 
            
            ax = fig.add_subplot(111)
            ax.set_facecolor('#fafafa') # 圖表繪圖區背景微灰
            
            # 移除座標軸刻度但保留邊框
            ax.set_xticks([])
            ax.set_yticks([])
            # 調整邊距
            fig.subplots_adjust(left=0.02, right=0.98, top=0.95, bottom=0.05)

            canvas = FigureCanvasTkAgg(fig, master=frame)
            chart_area = (fig, ax, canvas)
            
            canvas_widget = canvas.get_tk_widget()
            canvas_widget.grid(row=0, column=2, rowspan=1, padx=10, pady=5, sticky="e")
        else:
            ttk.Label(frame, text="(無圖表功能)").grid(row=0, column=2, padx=10)

        # 移除按鈕
        btn = ttk.Button(frame, text="移除", command=lambda c=code: self._remove_card(c))
        btn.grid(row=0, column=3, padx=5, sticky="n", pady=10)

        self.card_frames[code] = {
            "frame": frame,
            "price": price_lbl,
            "change": change_lbl,
            "details": details,
            "time": time_lbl,
            "chart": chart_area
        }
        self.price_history.setdefault(code, [])

    def _remove_card(self, code):
        if code in self.card_frames:
            self.card_frames[code]["frame"].destroy()
            del self.card_frames[code]
        if code in self.watchset:
            self.watchset.remove(code)

    def _crawler_worker(self):
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        while not self.stop_event.is_set():
            try:
                try:
                    task = self.task_queue.get(timeout=1)
                except queue.Empty:
                    continue
                
                cmd, payload = task
                if cmd == "FETCH":
                    self.result_queue.put(("START", len(payload)))
                    def on_progress(current, total):
                        self.result_queue.put(("PROGRESS", (current, total)))
                    results = loop.run_until_complete(crawl_stocks_async(payload, on_progress))
                    self.result_queue.put(("DATA", results))
                    self.result_queue.put(("DONE", None))
            except Exception as e:
                self.result_queue.put(("ERROR", str(e)))
        loop.close()

    def _process_queues(self):
        try:
            while True:
                msg_type, data = self.result_queue.get_nowait()
                if msg_type == "START":
                    self.status_var.set("更新中...")
                    self.update_btn.config(state=tk.DISABLED)
                    self.progress_bar.config(value=0, maximum=data)
                elif msg_type == "PROGRESS":
                    self.progress_bar.config(value=data[0])
                elif msg_type == "DATA":
                    self._update_ui_data(data)
                elif msg_type == "DONE":
                    self.status_var.set(f"更新完成 ({time.strftime('%H:%M:%S')})")
                    self.update_btn.config(state=tk.NORMAL)
                elif msg_type == "ERROR":
                    self.status_var.set(f"錯誤: {data}")
                    self.update_btn.config(state=tk.NORMAL)
        except queue.Empty:
            pass
        self.root.after(100, self._process_queues)

    def _update_ui_data(self, data_map: Dict):
        for code, data in data_map.items():
            if code not in self.card_frames: continue
            
            widgets = self.card_frames[code]
            try:
                price_str = data.get("即時價格", "0").replace(',', '')
                try:
                    price_val = float(price_str)
                except ValueError:
                    price_val = 0.0

                change = data.get("漲跌", "0")
                change_rate = data.get("漲跌百分比", "0%")
                update_time = data.get("日期時間", "")
                
                try:
                    chg_val = float(change)
                    color = "#d60000" if chg_val > 0 else "#008800" if chg_val < 0 else "black"
                    prefix = "▲" if chg_val > 0 else "▼" if chg_val < 0 else ""
                except:
                    color = "black"
                    prefix = ""

                widgets["price"].config(text=str(price_val), foreground=color)
                widgets["change"].config(text=f"{prefix} {change} ({change_rate})", foreground=color)
                widgets["time"].config(text=f"最後更新: {update_time}")
                widgets["details"].config(text=f"開: {data.get('開盤價','-')}  高: {data.get('最高價','-')}  低: {data.get('最低價','-')}  量: {data.get('成交量','-')}")

                # --- 圖表繪製核心邏輯 ---
                if HAS_MPL and widgets["chart"]:
                    hist = self.price_history[code]
                    hist.append(price_val)
                    if len(hist) > 30: hist.pop(0)
                    
                    fig, ax, canvas = widgets["chart"]
                    ax.clear() # 清除舊圖
                    
                    # 顏色設定
                    line_color = '#d60000' if hist[-1] >= hist[0] else '#008800'
                    
                    # 繪製折線與標記 (marker='.' 讓單一點也能顯示)
                    ax.plot(hist, color=line_color, linewidth=1.5, marker='.', markersize=4)
                    
                    # 繪製填充區域
                    if len(hist) > 1:
                        ax.fill_between(range(len(hist)), hist, min(hist)*0.995, color=line_color, alpha=0.1)
                    
                    # 自動調整 Y 軸範圍，避免線條貼底
                    if hist:
                        min_p, max_p = min(hist), max(hist)
                        span = (max_p - min_p) if max_p != min_p else max_p * 0.01
                        ax.set_ylim(min_p - span*0.5, max_p + span*0.5)

                    canvas.draw() # 執行重繪
            except Exception as e:
                print(f"Update error for {code}: {e}")

    def _trigger_update(self, codes=None):
        if not CRAWL4AI_AVAILABLE:
            messagebox.showwarning("錯誤", "未安裝 crawl4ai")
            return
        targets = codes if codes else list(self.watchset)
        if targets: self.task_queue.put(("FETCH", targets))

    def _on_manual_update(self):
        self._trigger_update()

    def _on_toggle_auto(self):
        if self.auto_var.get(): self._auto_update_loop()

    def _auto_update_loop(self):
        if not self.auto_var.get(): return
        self._trigger_update()
        self.root.after(60000, self._auto_update_loop)

    def _load_watchlist(self):
        if os.path.exists(self.WATCHLIST_FILE):
            try:
                with open(self.WATCHLIST_FILE, 'r', encoding='utf-8') as f:
                    for code in json.load(f):
                        if code not in self.watchset:
                            self.watchset.add(code)
                            self._create_card(code)
            except Exception: pass

    def _save_watchlist(self):
        try:
            with open(self.WATCHLIST_FILE, 'w', encoding='utf-8') as f:
                json.dump(list(self.watchset), f)
        except Exception: pass

    def _on_closing(self):
        self.stop_event.set()
        self._save_watchlist()
        self.root.destroy()

def main():
    root = tk.Tk()
    app = StockMonitorApp(root)
    root.mainloop()

if __name__ == "__main__":
    main()