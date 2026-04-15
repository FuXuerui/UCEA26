import re
import time
import pandas as pd
from playwright.sync_api import sync_playwright

URLS = [
    "https://www.alachuaschools.net/page/languageline",
    "https://www.alachuaschools.net/page/immigrantservices",
    "https://www.alachuaschools.net/page/esolcontacts",
    "https://www.alachuaschools.net/page/communicationplatforms",
]

KEYWORDS = [
    "language access policy",
    "translation services",
    "ell parent communication",
    "language line",
    "interpreter",
    "interpretation",
    "translation",
    "translator",
    "esol",
    "english learner",
    "immigrant family",
    "parent",
    "communication",
]

DATE_PATTERNS = [
    r"\b(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\.?\s+\d{1,2},\s+\d{4}\b",
    r"\b\d{1,2}/\d{1,2}/\d{2,4}\b",
    r"\b\d{4}-\d{2}-\d{2}\b",
]

SCHOOL_PATTERN = re.compile(
    r"\b([A-Z][A-Za-z&'\-]+(?:\s+[A-Z][A-Za-z&'\-]+){0,6}\s+"
    r"(?:Elementary|Middle|High|School|Academy|Center))\b"
)

def normalize_text(text: str) -> str:
    if not text:
        return ""
    return re.sub(r"\s+", " ", text).strip()

def find_hits(text: str, keywords: list[str]) -> list[str]:
    text_low = text.lower()
    return [kw for kw in keywords if kw.lower() in text_low]

def extract_date(text: str) -> str:
    for pattern in DATE_PATTERNS:
        m = re.search(pattern, text, flags=re.IGNORECASE)
        if m:
            return m.group(0)
    return ""

def extract_school_name(text: str) -> str:
    matches = SCHOOL_PATTERN.findall(text)
    if matches:
        return list(dict.fromkeys(matches))[0]
    return ""

def get_rendered_page_data(page, url: str) -> dict:
    try:
        # 不要再用 networkidle
        page.goto(url, wait_until="domcontentloaded", timeout=60000)

        # 给 JS 一点额外时间
        page.wait_for_timeout(5000)

        title = page.title()
        body_text = normalize_text(page.locator("body").inner_text())

        hits = find_hits(body_text, KEYWORDS)
        doc_time = extract_date(body_text)
        school_name = extract_school_name(body_text)

        return {
            "url": url,
            "title": title,
            "matched_keywords": "; ".join(hits),
            "document_time": doc_time,
            "school_name": school_name,
            "text_preview": body_text[:1500],
            "text_length": len(body_text),
            "status": "ok",
        }

    except Exception as e:
        return {
            "url": url,
            "title": "",
            "matched_keywords": "",
            "document_time": "",
            "school_name": "",
            "text_preview": "",
            "text_length": 0,
            "status": f"error: {e}",
        }

def main():
    rows = []

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=False,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--disable-dev-shm-usage",
                "--no-sandbox",
            ],
        )

        page = browser.new_page()

        for url in URLS:
            print(f"[CHECK] {url}")
            row = get_rendered_page_data(page, url)
            print(f"  -> {row['status']}")
            print(f"     text_length = {row['text_length']}")
            if row["matched_keywords"]:
                print(f"     HIT: {row['matched_keywords']}")
            rows.append(row)
            time.sleep(1)

        browser.close()

    df = pd.DataFrame(rows)

    # 换一个新文件名，避免 Excel 正在占用旧文件
    out_file = "demo_playwright_results.xlsx"
    df.to_excel(out_file, index=False)
    print(f"\nSaved to: {out_file}")

if __name__ == "__main__":
    main()