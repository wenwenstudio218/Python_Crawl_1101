import tkinter as tk
from tkinter import ttk
import threading
import queue
import json
import os
import time
import random
import asyncio
import re
try:
    import matplotlib
    matplotlib.use('Agg')
    from matplotlib.figure import Figure
    from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
    HAS_MPL = True
except Exception:
    HAS_MPL = False


class StockMonitorApp:
    WATCHLIST_FILE = os.path.join(os.path.dirname(__file__), "watchlist.json")

    def __init__(self, root):
        self.root = root
        self.root.title("股票即時監控（範例）")
        self.root.geometry("900x600")

        self.stop_event = threading.Event()
        self.update_queue = queue.Queue()
        self.fetch_lock = threading.Lock()
        self.cache = {}  # code -> (timestamp, data)
        self.cache_ttl = 20  # seconds

        self.watchset = set()
        self.card_frames = {}
        self.price_history = {}  # code -> list of recent prices

        self._build_ui()
        self._load_watchlist()

        # 啟動背景更新執行緒（模擬）
        self.bg_thread = threading.Thread(target=self._background_update_loop, daemon=True)
        self.bg_thread.start()

        # 啟動主執行緒的 queue poll
        self._poll_queue()

        self.root.protocol("WM_DELETE_WINDOW", self._on_closing)

    def _build_ui(self):
        # 工具列（手動更新、自動更新）
        toolbar = ttk.Frame(self.root)
        toolbar.pack(fill=tk.X)

        self.update_btn = ttk.Button(toolbar, text="手動更新", command=self._on_manual_update)
        self.update_btn.pack(side=tk.LEFT, padx=6, pady=6)

        self.auto_var = tk.BooleanVar(value=False)
        self.auto_check = ttk.Checkbutton(toolbar, text="自動更新 (60s)", variable=self.auto_var, command=self._on_toggle_auto)
        self.auto_check.pack(side=tk.LEFT, padx=6)

        self.progress = ttk.Progressbar(toolbar, mode="determinate")
        self.progress.pack(side=tk.RIGHT, padx=8)

        paned = ttk.PanedWindow(self.root, orient=tk.HORIZONTAL)
        paned.pack(fill=tk.BOTH, expand=True)

        # 左側：股票選擇
        left_frame = ttk.Frame(paned, width=280)
        paned.add(left_frame, weight=1)

        search_label = ttk.Label(left_frame, text="搜尋 (代碼或名稱)")
        search_label.pack(anchor=tk.W, padx=8, pady=(8, 0))

        self.search_var = tk.StringVar()
        search_entry = ttk.Entry(left_frame, textvariable=self.search_var)
        search_entry.pack(fill=tk.X, padx=8, pady=4)
        search_entry.bind("<KeyRelease>", self._on_search)

        self.stock_listbox = tk.Listbox(left_frame, height=25)
        self.stock_listbox.pack(fill=tk.BOTH, expand=True, padx=8, pady=4)
        self.stock_listbox.bind('<Double-Button-1>', self._on_listbox_double)

        add_btn = ttk.Button(left_frame, text="加入觀察", command=self._on_add_button)
        add_btn.pack(fill=tk.X, padx=8, pady=(0, 8))

        # 右側：股票卡片顯示（可滾動）
        right_frame = ttk.Frame(paned)
        paned.add(right_frame, weight=4)

        self.canvas = tk.Canvas(right_frame)
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

        # 狀態列
        status = ttk.Frame(self.root)
        status.pack(fill=tk.X)
        self.status_label = ttk.Label(status, text="準備就緒")
        self.status_label.pack(side=tk.LEFT, padx=8, pady=4)

        # 初始化本地股票清單（示範）
        self.all_stocks = self._get_sample_stock_list()
        # 建立 code->name map
        self.stock_name_map = {code: name for code, name in self.all_stocks}
        self._refresh_stock_listbox()

    def _get_sample_stock_list(self):
        # 嘗試從 twstock 取得完整台灣股票清單，若失敗則回退到內建範例資料
        try:
            import twstock
            codes = getattr(twstock, 'codes', None)
            result = []
            if isinstance(codes, dict):
                for k, v in codes.items():
                    # twstock.codes 的 value 可能為字串或 dict
                    name = None
                    if isinstance(v, str):
                        name = v
                    elif isinstance(v, dict):
                        name = v.get('name') or v.get('short_name') or v.get('股票名稱') or str(v)
                    else:
                        # 嘗試從常見屬性擷取
                        for attr in ('name', 'chName', 'short_name', 'fullname', 'title', 'stock_name', 'sname'):
                            name = getattr(v, attr, None)
                            if name:
                                break
                        # 若是 namedtuple，嘗試 _asdict()
                        if name is None and hasattr(v, '_asdict'):
                            try:
                                d = v._asdict()
                                for key in ('name', 'chName', 'short_name', 'fullname'):
                                    if key in d and d[key]:
                                        name = d[key]
                                        break
                            except Exception:
                                pass
                        # 最後透過 repr / str 嘗試用 regex 擷取 name 欄位
                        if name is None:
                            s = str(v)
                            m = re.search(r"name=['\"]([^'\"]+)['\"]", s)
                            if not m:
                                m = re.search(r"chName=['\"]([^'\"]+)['\"]", s)
                            if not m:
                                m = re.search(r"short_name=['\"]([^'\"]+)['\"]", s)
                            if m:
                                name = m.group(1)
                        if name is None:
                            name = str(v)
                    result.append((k, name))
                # 依代碼排序並回傳
                return sorted(result, key=lambda x: x[0])

            # 若 twstock.codes 不存在或不是 dict，嘗試使用 twstock.stock 相關屬性
            stock_module = getattr(twstock, 'stock', None)
            if stock_module and hasattr(stock_module, 'codes'):
                sc = getattr(stock_module, 'codes')
                if isinstance(sc, dict):
                    return sorted([(k, v if isinstance(v, str) else str(v)) for k, v in sc.items()], key=lambda x: x[0])

        except Exception:
            # 若載入 twstock 或解析失敗，會使用範例資料
            pass

        # 預設小型範例清單
        return [
            ("2330", "台積電"),
            ("2317", "鴻海"),
            ("2412", "中華電"),
            ("2454", "聯發科"),
            ("2881", "富邦金"),
            ("2882", "國泰金"),
        ]

    def _refresh_stock_listbox(self, filter_text=""):
        self.stock_listbox.delete(0, tk.END)
        ft = filter_text.strip().lower()
        for code, name in self.all_stocks:
            label = f"{code} - {name}"
            if not ft or ft in code or ft in name.lower():
                self.stock_listbox.insert(tk.END, label)

    def _on_search(self, event=None):
        q = self.search_var.get()
        self._refresh_stock_listbox(q)

    def _on_listbox_double(self, event=None):
        sel = self.stock_listbox.curselection()
        if not sel:
            return
        text = self.stock_listbox.get(sel[0])
        code = text.split(" - ")[0]
        self._add_watch(code)

    def _on_add_button(self):
        sel = self.stock_listbox.curselection()
        if not sel:
            self._set_status("請先選擇一支股票再加入")
            return
        text = self.stock_listbox.get(sel[0])
        code = text.split(" - ")[0]
        self._add_watch(code)

    def _add_watch(self, code):
        if code in self.watchset:
            self._set_status(f"{code} 已在觀察清單中")
            return
        self.watchset.add(code)
        # 產生卡片
        self._create_stock_card(code)
        self._set_status(f"已加入 {code}")

    def _create_stock_card(self, code):
        if code in self.card_frames:
            return
        frame = ttk.Frame(self.scrollable_frame, relief=tk.RIDGE, borderwidth=1, padding=8)
        frame.pack(fill=tk.X, padx=8, pady=6)

        # 標題：代碼 + 名稱
        name = self.stock_name_map.get(code, '')
        title_text = f"{code} {name}" if name else code
        title = ttk.Label(frame, text=title_text, font=(None, 12, "bold"))
        title.grid(row=0, column=0, sticky=tk.W)

        # 價格區塊：大型字體
        price_lbl = ttk.Label(frame, text="價格：--", font=(None, 16, "bold"))
        price_lbl.grid(row=1, column=0, sticky=tk.W, pady=(4, 0))

        change_lbl = ttk.Label(frame, text="漲跌：--")
        change_lbl.grid(row=1, column=1, sticky=tk.W, padx=12)

        # 圖表區（若有 matplotlib）
        chart_widget = None
        if HAS_MPL:
            fig = Figure(figsize=(3, 0.9), dpi=80)
            ax = fig.add_subplot(111)
            ax.set_xticks([])
            ax.set_yticks([])
            fig.tight_layout()
            canvas = FigureCanvasTkAgg(fig, master=frame)
            canvas_widget = canvas.get_tk_widget()
            canvas_widget.grid(row=0, column=3, rowspan=3, padx=8, sticky=tk.N)
            chart_widget = (fig, ax, canvas)

        time_lbl = ttk.Label(frame, text="更新：--")
        time_lbl.grid(row=2, column=0, sticky=tk.W, pady=(4, 0))

        remove_btn = ttk.Button(frame, text="移除", command=lambda c=code: self._remove_watch(c))
        remove_btn.grid(row=0, column=2, sticky=tk.E)

        self.card_frames[code] = {
            "frame": frame,
            "title": title,
            "price_lbl": price_lbl,
            "change_lbl": change_lbl,
            "time_lbl": time_lbl,
            "chart": chart_widget,
        }
        # 初始化價格歷史
        self.price_history.setdefault(code, [])

    def _remove_watch(self, code):
        if code not in self.watchset:
            return
        self.watchset.remove(code)
        widgets = self.card_frames.pop(code, None)
        if widgets:
            widgets["frame"].destroy()
        self._set_status(f"已移除 {code}")

    def _set_status(self, text):
        self.status_label.config(text=text)

    def _background_update_loop(self):
        """
        模擬背景爬蟲或即時資料更新：定期產生隨機價格並放入 queue，實際整合時改為非同步爬蟲或 crawl4ai。
        """
        while not self.stop_event.is_set():
            if not self.watchset:
                time.sleep(1)
                continue
            # 模擬逐支更新
            for code in list(self.watchset):
                data = self._simulate_fetch(code)
                self.update_queue.put((code, data))
            # 等待下一輪
            for _ in range(10):
                if self.stop_event.is_set():
                    break
                time.sleep(1)

    def _simulate_fetch(self, code):
        # 回傳模擬資料結構
        price = round(100 * random.uniform(0.5, 2.0), 2)
        change = round(random.uniform(-5, 5), 2)
        ts = time.strftime("%Y-%m-%d %H:%M:%S")
        return {"price": price, "change": change, "time": ts}

    def _fetch_with_twstock(self, code):
        """使用 twstock.realtime.get 同步取得資料，回傳與模擬相同的欄位結構。
        若未安裝 twstock，會 raise ImportError。
        """
        try:
            import twstock
            from twstock import realtime
        except Exception as e:
            raise ImportError("twstock 未安裝，請執行 `pip install twstock`") from e

        try:
            r = realtime.get(code)
        except Exception as e:
            raise RuntimeError(f"twstock.realtime.get 失敗: {e}") from e

        # 解析回傳
        rt = r.get("realtime") if isinstance(r, dict) else None
        price = None
        change = None
        tstamp = None

        if rt:
            # latest_trade 可能為字串
            latest = rt.get("latest_trade") or rt.get("trade_price") or rt.get("price")
            prev = rt.get("previous_close") or rt.get("pre_close")
            latest_time = rt.get("latest_trade_time")
            try:
                if latest is not None:
                    price = float(latest)
            except Exception:
                price = None
            try:
                if prev is not None and price is not None:
                    change = round(price - float(prev), 2)
            except Exception:
                change = None
            tstamp = latest_time

        # 若解析失敗，退回模擬
        if price is None:
            return self._simulate_fetch(code)

        if not tstamp:
            tstamp = time.strftime("%Y-%m-%d %H:%M:%S")

        return {"price": price, "change": change if change is not None else 0.0, "time": tstamp}

    async def fetch_stock_info(self, code, semaphore: asyncio.Semaphore, retries: int = 2, timeout: int = 10):
        """非同步取得單支股票資料。若安裝 twstock，可在此處改為真正抓取。"""
        # 快取檢查
        now = time.time()
        cached = self.cache.get(code)
        if cached and now - cached[0] < self.cache_ttl:
            return cached[1]
        attempt = 0
        while attempt <= retries:
            attempt += 1
            try:
                async with semaphore:
                    # 先嘗試使用 twstock，如果不可用則退回模擬
                    try:
                        data = await asyncio.to_thread(self._fetch_with_twstock, code)
                    except ImportError:
                        # 通知使用者需要安裝 twstock（但仍使用模擬以不中斷流程）
                        self.update_queue.put(("__error__", {"code": code, "error": "twstock 未安裝，使用模擬資料。請執行: pip install twstock"}))
                        data = await asyncio.to_thread(self._simulate_fetch, code)
                    except Exception:
                        # 其他錯誤：向外拋出讓外層處理或重試
                        raise

                # 更新快取並回傳
                self.cache[code] = (time.time(), data)
                return data
            except Exception:
                if attempt > retries:
                    raise
                await asyncio.sleep(0.5)

    async def fetch_multiple_stocks(self, codes, concurrency: int = 5):
        sem = asyncio.Semaphore(concurrency)
        total = len(codes)
        results = {}

        async def _wrap(code, idx):
            try:
                data = await self.fetch_stock_info(code, sem)
                # 直接把每支的更新傳回主執行緒 queue
                self.update_queue.put((code, data))
                # 傳送進度訊息
                self.update_queue.put(("__progress__", {"done": idx + 1, "total": total}))
            except Exception as e:
                self.update_queue.put(("__error__", {"code": code, "error": str(e)}))

        tasks = [ _wrap(code, i) for i, code in enumerate(codes) ]
        await asyncio.gather(*tasks)
        # 標記完成
        self.update_queue.put(("__fetch_done__", None))

    def _run_async_fetch_in_thread(self, codes):
        """在背景執行緒中以 asyncio.run 執行非同步抓取，避免阻塞主執行緒。"""
        try:
            asyncio.run(self.fetch_multiple_stocks(codes))
        except Exception as e:
            self.update_queue.put(("__error__", {"code": None, "error": str(e)}))

    def _on_manual_update(self):
        if not self.watchset:
            self._set_status("觀察清單為空，無需更新")
            return
        # 避免同時多次觸發
        if not self.fetch_lock.acquire(blocking=False):
            self._set_status("已有更新進行中，請稍候")
            return
        self.update_btn.config(state=tk.DISABLED)
        self.progress.config(maximum=len(self.watchset), value=0)
        self._set_status("開始更新...")
        codes = list(self.watchset)
        t = threading.Thread(target=self._run_async_fetch_in_thread, args=(codes,), daemon=True)
        t.start()

    def _on_toggle_auto(self):
        if self.auto_var.get():
            self._set_status("自動更新已啟動 (60s)")
            self._schedule_auto()
        else:
            self._set_status("自動更新已停止")

    def _schedule_auto(self):
        if not self.auto_var.get():
            return
        # 每 60 秒執行一次
        self._on_manual_update()
        self.root.after(60 * 1000, self._schedule_auto)

    def _poll_queue(self):
        try:
            while True:
                code, data = self.update_queue.get_nowait()
                # 處理特殊訊息
                if code == "__progress__":
                    info = data
                    done = info.get("done", 0)
                    total = info.get("total", 1)
                    try:
                        self.progress.config(value=done, maximum=total)
                    except Exception:
                        pass
                    continue
                if code == "__fetch_done__":
                    self._set_status("更新完成")
                    self.update_btn.config(state=tk.NORMAL)
                    try:
                        self.fetch_lock.release()
                    except Exception:
                        pass
                    continue
                if code == "__error__":
                    err = data
                    self._set_status(f"錯誤: {err.get('error')}")
                    self.update_btn.config(state=tk.NORMAL)
                    try:
                        self.fetch_lock.release()
                    except Exception:
                        pass
                    continue

                self._apply_update(code, data)
        except queue.Empty:
            pass
        # 每 500ms 檢查一次
        self.root.after(500, self._poll_queue)

    def _apply_update(self, code, data):
        if code not in self.card_frames:
            return
        widgets = self.card_frames[code]
        price = data.get('price')
        change = data.get('change')
        ts = data.get('time')

        # 顯示價格與時間
        widgets["price_lbl"].config(text=f"價格：{price}")
        widgets["time_lbl"].config(text=f"更新：{ts}")

        # 漲跌顏色：正為紅、負為綠、0為黑
        try:
            ch_val = float(change)
            if ch_val > 0:
                fg = "#c40000"
            elif ch_val < 0:
                fg = "#007a00"
            else:
                fg = "black"
        except Exception:
            fg = "black"
        widgets["change_lbl"].config(text=f"漲跌：{change}", foreground=fg)

        # 更新價格歷史並重繪圖表（若支援）
        try:
            if price is not None:
                hist = self.price_history.setdefault(code, [])
                hist.append(float(price))
                if len(hist) > 30:
                    hist.pop(0)
                if widgets.get('chart') and HAS_MPL:
                    fig, ax, canvas = widgets['chart']
                    ax.clear()
                    ax.plot(hist, linewidth=1, color='#1f77b4')
                    ax.fill_between(range(len(hist)), hist, [min(hist)]*len(hist), color='#cfe9ff', alpha=0.4)
                    ax.set_xticks([])
                    ax.set_yticks([])
                    fig.tight_layout()
                    canvas.draw()
        except Exception:
            pass

    def _load_watchlist(self):
        try:
            if os.path.exists(self.WATCHLIST_FILE):
                with open(self.WATCHLIST_FILE, "r", encoding="utf-8") as f:
                    items = json.load(f)
                    for code in items:
                        self.watchset.add(code)
                        self._create_stock_card(code)
                self._set_status("已載入觀察清單")
            else:
                self._set_status("尚無觀察清單，請加入股票")
        except Exception as e:
            self._set_status(f"載入觀察清單失敗: {e}")

    def _save_watchlist(self):
        try:
            with open(self.WATCHLIST_FILE, "w", encoding="utf-8") as f:
                json.dump(list(self.watchset), f, ensure_ascii=False, indent=2)
            self._set_status("觀察清單已儲存")
        except Exception as e:
            self._set_status(f"儲存觀察清單失敗: {e}")

    def _on_closing(self):
        self._set_status("正在關閉，請稍候...")
        self.stop_event.set()
        # 等待背景執行緒結束（短暫）
        if self.bg_thread.is_alive():
            self.bg_thread.join(timeout=2)
        self._save_watchlist()
        self.root.destroy()


def main():
    root = tk.Tk()
    app = StockMonitorApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
