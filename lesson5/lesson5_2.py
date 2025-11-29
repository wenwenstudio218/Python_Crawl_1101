import os
from playwright.sync_api import sync_playwright


def main():
    path = "https://www.thsrc.com.tw/"
    with sync_playwright() as p:
        browser = p.chromium.launch(headless = False, slow_mo = 500)
        page = browser.new_page()
        page.goto(path)

        page.wait_for_load_state("domcontentloaded")
        page.locator("button",has_text="我同意").click()
        page.wait_for_timeout(3000)

        browser.close()

if __name__ == "__main__":
    main()