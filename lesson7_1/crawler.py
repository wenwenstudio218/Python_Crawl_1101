import re
import asyncio
from typing import List, Dict, Any

try:
    from crawl4ai import AsyncWebCrawler, CrawlerRunConfig, CacheMode, JsonCssExtractionStrategy
    _HAS_CRAWL4AI = True
except Exception:
    _HAS_CRAWL4AI = False

import requests
from bs4 import BeautifulSoup
from datetime import datetime


def _parse_bot_html(html: str) -> List[Dict[str, Any]]:
    soup = BeautifulSoup(html, "html.parser")
    table = soup.select_one("table[title='牌告匯率']")
    rows = []
    if not table:
        return rows

    trs = table.select("tr")
    for tr in trs[1:]:
        tds = tr.find_all("td")
        if not tds:
            continue
        currency_text = tds[0].get_text(" ", strip=True)
        m = re.search(r"([A-Z]{3})", currency_text)
        code = m.group(1) if m else currency_text

        def _clean(td_idx):
            try:
                txt = tds[td_idx].get_text(strip=True)
                return txt if txt and txt != "-" else None
            except Exception:
                return None

        cash_buy = _clean(1)
        cash_sell = _clean(2)
        spot_buy = _clean(3)
        spot_sell = _clean(4)

        tradable = any([cash_buy, cash_sell, spot_buy, spot_sell])

        rows.append(
            {
                "currency": currency_text,
                "code": code,
                "cash_buy": cash_buy,
                "cash_sell": cash_sell,
                "spot_buy": spot_buy,
                "spot_sell": spot_sell,
                "tradable": tradable,
            }
        )

    return rows


def fetch_rates() -> Dict[str, Any]:
    """抓取匯率並回傳 dict: { 'rates': [...], 'fetched_at': ISO }

    優先使用 crawl4ai（若可用），否則使用 requests + BeautifulSoup 後備方案。
    """
    url = "https://rate.bot.com.tw/xrt?Lang=zh-TW"
    fetched_at = datetime.utcnow().isoformat() + "Z"

    if _HAS_CRAWL4AI:
        try:
            schema = [
                {
                    "name": "匯率資訊",
                    "baseSelector": "table[title='牌告匯率'] tr",
                    "columns": [
                        {"name": "currency", "selector": "td:nth-child(1)"},
                        {"name": "cash_buy", "selector": "td:nth-child(2)"},
                        {"name": "cash_sell", "selector": "td:nth-child(3)"},
                        {"name": "spot_buy", "selector": "td:nth-child(4)"},
                        {"name": "spot_sell", "selector": "td:nth-child(5)"},
                    ],
                }
            ]

            strategy = JsonCssExtractionStrategy(schema)
            crawler = AsyncWebCrawler()
            cfg = CrawlerRunConfig(
                start_urls=[url],
                cache_mode=CacheMode.NO_CACHE,
                strategies=[strategy],
            )

            result = asyncio.get_event_loop().run_until_complete(crawler.arun(cfg))
            rows = []
            for page in result:
                for item in page.get("匯率資訊", []):
                    rows.append(
                        {
                            "currency": item.get("currency", "").strip(),
                            "code": (re.search(r"([A-Z]{3})", item.get("currency", "")) or [None])[0],
                            "cash_buy": item.get("cash_buy") or None,
                            "cash_sell": item.get("cash_sell") or None,
                            "spot_buy": item.get("spot_buy") or None,
                            "spot_sell": item.get("spot_sell") or None,
                            "tradable": any([item.get("cash_buy"), item.get("cash_sell"), item.get("spot_buy"), item.get("spot_sell")]),
                        }
                    )

            return {"rates": rows, "fetched_at": fetched_at}
        except Exception:
            pass

    try:
        resp = requests.get(url, timeout=15)
        resp.raise_for_status()
        rows = _parse_bot_html(resp.text)
        return {"rates": rows, "fetched_at": fetched_at}
    except Exception as e:
        return {"rates": [], "fetched_at": fetched_at, "error": str(e)}


if __name__ == "__main__":
    import json

    out = fetch_rates()
    print(json.dumps(out, ensure_ascii=False, indent=2))
