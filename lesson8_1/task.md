# 任務清單：股票即時監控桌面應用程式

## 簡短摘要
- 目標：建立基於 `tkinter` 的台灣股票即時監控桌面應用程式，採用 `crawl4ai` 非同步爬蟲並以 `twstock` 提供股票代碼資料。主要重點為：非同步爬蟲模組、背景爬蟲與 UI 的橋接、以及每分鐘自動/手動更新與錯誤處理。

---

## 任務清單（可直接執行的條目，估時與優先順序）

- **設定與相依性清單**: 列出並驗證所需套件（`crawl4ai`、`twstock`、`uv` 等），建立安裝指引與 `requirements.txt` 或更新 `pyproject.toml`。
  - **檔案/輸出**: `lesson8_1/requirements.txt` 或專案根目錄 `pyproject.toml` 更新
  - **依賴**: `crawl4ai`, `twstock`, `uv`（開發）、系統 Chromium（二進位，視情況）
  - **風險/注意事項**: Windows 可能需額外說明 headless 瀏覽器安裝
  - **優先順序**: 高
  - **估時**: S (0.5–2 小時)

- **檢閱爬蟲 selector**: 檢查 `lesson8_1/lesson8_1_3.py` 中的 selector 與等待邏輯，將 selector 參數化便於未來調整
  - **檔案/輸出**: `lesson8_1/lesson8_1_3.py`（註記或建立 `selectors.json`）
  - **依賴**: 無
  - **風險/注意事項**: 目標網站 DOM 變更時需更新 selector
  - **優先順序**: 高
  - **估時**: S (0.5–2 小時)

- **單支抓取函式**: 實作穩定的單一股票抓取函式（含重試、timeout、錯誤分類），標準化回傳格式
  - **檔案/輸出**: `lesson8_1/crawler.py`（單一函式 `fetch_stock()`）
  - **依賴**: `crawl4ai`, `asyncio`
  - **風險/注意事項**: 過度頻繁的請求可能違反目標網站使用條款
  - **優先順序**: 高
  - **估時**: M (2–4 小時)

- **並行爬取管理器**: 建立可設定並行數的 manager（Semaphore、重試策略），統一輸出摘要
  - **檔案/輸出**: `lesson8_1/crawler.py`（class/manager）
  - **依賴**: `asyncio`
  - **風險/注意事項**: 並行數過高會耗盡本機/伺服器資源
  - **優先順序**: 高
  - **估時**: M (2–4 小時)

- **背景爬蟲與 UI 橋接**: 在背景執行緒內啟動 asyncio loop，使用 `queue.Queue` 或 callback 將結果回傳到主執行緒（確保 UI 更新僅在主執行緒）
  - **檔案/輸出**: `lesson8_1/bridge.py` 或整合於 `lesson8_1/main.py`
  - **依賴**: `threading`, `queue`, `asyncio`
  - **風險/注意事項**: 必須避免在非主執行緒直接更新 `tkinter`
  - **優先順序**: 高
  - **估時**: M (2–4 小時)

- **UI 骨架（左右面板）**: 建立 `tkinter` 主視窗與左右面板佈局（左側搜尋/清單，右側觀察清單顯示）
  - **檔案/輸出**: `lesson8_1/main.py`
  - **依賴**: `tkinter`, `twstock`（顯示清單）
  - **風險/注意事項**: 需妥善處理動態新增元素與滾動條
  - **優先順序**: 高
  - **估時**: M (2–4 小時)

- **股票搜尋與加入功能**: 使用 `twstock` 提供代碼/名稱查詢，實作搜尋欄、搜尋結果與「加入」按鈕
  - **檔案/輸出**: `lesson8_1/main.py`
  - **依賴**: `twstock`
  - **風險/注意事項**: `twstock` 資料不完整時要有 fallback 顯示
  - **優先順序**: 高
  - **估時**: M (2–4 小時)

- **觀察清單顯示與移除**: 在右側面板顯示每支股票的即時資訊並提供「移除」按鈕
  - **檔案/輸出**: `lesson8_1/main.py`
  - **依賴**: Crawler bridge、UI
  - **風險/注意事項**: 頻繁更新時需採用差分更新以避免閃爍
  - **優先順序**: 高
  - **估時**: M (2–4 小時)

- **自動與手動更新**: 使用 `tkinter.after()` 實作每分鐘自動更新，並提供手動立即更新按鈕（含更新鎖）
  - **檔案/輸出**: `lesson8_1/main.py`、bridge
  - **依賴**: `tkinter`, bridge
  - **風險/注意事項**: 防止重複更新導致 race condition
  - **優先順序**: 高
  - **估時**: S (0.5–2 小時)

- **觀察清單持久化（可選）**: 儲存/載入觀察清單 (`lesson8_1/watchlist.json`)
  - **檔案/輸出**: `lesson8_1/watchlist.json`
  - **依賴**: `json`, 檔案系統
  - **風險/注意事項**: 檔案毀損需容錯處理
  - **優先順序**: 中
  - **估時**: S (0.5–2 小時)

- **錯誤處理與使用者通知**: 捕捉網路/解析錯誤，個別股票失敗不影響其他，UI 顯示錯誤提示
  - **檔案/輸出**: `lesson8_1/main.py`, `lesson8_1/crawler.py`
  - **依賴**: logging
  - **風險/注意事項**: UI 訊息須簡潔明確
  - **優先順序**: 高
  - **估時**: M (2–3 小時)

- **Windows headless 測試與說明**: 在 Windows 測試 headless 設定，撰寫安裝 Chromium 與執行指引（含 `run_windows.bat` 或 README）
  - **檔案/輸出**: `README.md` 或 `lesson8_1/README_WINDOWS.md`, `run_windows.bat`
  - **依賴**: Chromium 二進位
  - **風險/注意事項**: 使用者環境差異導致 headless 設定失敗
  - **優先順序**: 高
  - **估時**: M (2–4 小時)

- **整合與效能優化**: 最小更新策略、並行數調整選項、完成 README 與測試
  - **檔案/輸出**: `lesson8_1/main.py`, `lesson8_1/crawler.py`, `README.md`
  - **依賴**: 無額外套件
  - **風險/注意事項**: 需平衡即時性與資源使用
  - **優先順序**: 中
  - **估時**: M (2–4 小時)

---

## 需要您確認的問題
1. 是否要啟用觀察清單持久化（預設儲存在 `lesson8_1/watchlist.json`）？
2. 資料來源是否固定為單一來源（例如 plan 中的 `wantgoo.com`），或需一開始就支援多來源 adapter？
3. 是否允許在 Windows 上安裝 Chromium（以支援 headless 模式）？

---

## 建議的 MVP 範圍（第一版優先項目）
- `lesson8_1/requirements.txt`（或更新 `pyproject.toml`）
- `lesson8_1/crawler.py`（單支抓取 + 並行管理）
- `lesson8_1/main.py`（tkinter UI 骨架、搜尋/加入/觀察清單顯示）
- 背景橋接（thread + queue）、每分鐘自動更新與手動刷新

若您同意，我將從第 2 項（檢閱爬蟲 selector）或第 3 項（單支抓取函式）開始實作，請回覆您優先想要的起點。