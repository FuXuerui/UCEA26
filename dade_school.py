import re
import time
from urllib.parse import quote, urljoin, urlparse

import pandas as pd
from playwright.sync_api import sync_playwright


# =========================
# 1. 基础配置
# =========================
SEARCH_BASE = "https://www.dadeschools.net/SiteSearch?q="

SEARCH_KEYWORDS = [
    "translation",
    "interpretation",
    "language support",
    "language service",
    "language assistance",
    "language line",
    "language access",
    "parent communication",
    "on-demand interpretation",
    "video interpretation",
    "telephone interpreting",
    "translating",
    "interpreting",
    "translate",
    "interpret",
]

ALLOWED_DOMAINS = [
    "www.dadeschools.net",
    "dadeschools.net",
    "news.dadeschools.net",
    "ehandbooks.dadeschools.net",
    "forms.dadeschools.net",
    "pdfs.dadeschools.net",
    "oat.dadeschools.net",
    "attendanceservices.dadeschools.net",
    "districtartifacts.dadeschools.net",
]

KEYWORDS = [
    "translation",
    "interpretation",
    "language support",
    "language service",
    "language assistance",
    "language line",
    "language access",
    "parent communication",
    "on-demand interpretation",
    "video interpretation",
    "telephone interpreting",
    "translating",
    "interpreting",
    "translate",
    "interpret",
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


# =========================
# 2. 文本处理函数
# =========================
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


# =========================
# 3. URL 相关函数
# =========================
def build_search_url(base_search_url: str, keyword: str) -> str:
    return f"{base_search_url}{quote(keyword)}"


def is_allowed_domain(url: str, allowed_domains: list[str]) -> bool:
    try:
        netloc = urlparse(url).netloc.lower()
        return any(netloc == d or netloc.endswith("." + d) for d in allowed_domains)
    except Exception:
        return False


def should_skip_url(url: str) -> bool:
    url_low = url.lower()

    skip_patterns = [
        "mailto:",
        "tel:",
        "javascript:",
        "facebook.com",
        "instagram.com",
        "twitter.com",
        "x.com",
        "youtube.com",
        "linkedin.com",
        ".jpg",
        ".jpeg",
        ".png",
        ".gif",
        ".mp4",
        ".mp3",
        ".zip",
    ]

    return any(p in url_low for p in skip_patterns)


# =========================
# 4. 从搜索结果页提取链接
# =========================
def collect_search_result_links(
    page,
    base_url: str,
    allowed_domains: list[str],
    max_links: int = 20,
) -> list[str]:
    results = []

    try:
        links = page.locator("a")
        n = links.count()
    except Exception:
        return []

    for i in range(n):
        try:
            a = links.nth(i)
            href = a.get_attribute("href")
            text = normalize_text(a.inner_text())

            if not href:
                continue

            full_url = urljoin(base_url, href)

            if should_skip_url(full_url):
                continue

            if not is_allowed_domain(full_url, allowed_domains):
                continue

            full_url_low = full_url.lower()

            # 排除搜索页自己、首页、明显导航页
            if "sitesearch" in full_url_low:
                continue

            if full_url_low.rstrip("/") in [
                "https://www.dadeschools.net",
                "https://www.dadeschools.net/home",
                "https://dadeschools.net",
                "https://dadeschools.net/home",
            ]:
                continue

            if len(text) >= 2:
                results.append(full_url)

        except Exception:
            continue

    results = list(dict.fromkeys(results))
    return results[:max_links]


# =========================
# 5. 页面正文抓取
# =========================
def get_rendered_page_data(page, url: str) -> dict:
    try:
        page.goto(url, wait_until="domcontentloaded", timeout=60000)
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
            "text_preview": body_text[:2000],
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


# =========================
# 6. 主程序
# =========================
def main():
    rows = []
    visited_urls = set()

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=False,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--disable-dev-shm-usage",
                "--no-sandbox",
            ],
        )

        context = browser.new_context()
        page = context.new_page()

        for kw in SEARCH_KEYWORDS:
            search_url = build_search_url(SEARCH_BASE, kw)

            print(f"[SEARCH] {kw}")
            print(f"         {search_url}")

            try:
                page.goto(search_url, wait_until="domcontentloaded", timeout=60000)
                page.wait_for_timeout(5000)
            except Exception as e:
                print(f"  -> search page error: {e}")
                continue

            result_links = collect_search_result_links(
                page=page,
                base_url=search_url,
                allowed_domains=ALLOWED_DOMAINS,
                max_links=20,
            )

            print(f"  -> found {len(result_links)} result links")

            for link in result_links:
                print(f"     {link}")

            for url in result_links:
                if url in visited_urls:
                    continue

                visited_urls.add(url)

                print(f"[CHECK] {url}")
                row = get_rendered_page_data(page, url)
                row["search_keyword"] = kw

                print(f"  -> {row['status']}")
                print(f"     text_length = {row['text_length']}")
                if row["matched_keywords"]:
                    print(f"     HIT: {row['matched_keywords']}")

                rows.append(row)
                time.sleep(1)

        browser.close()

    df = pd.DataFrame(rows)
    out_file = "dade_search_results.xlsx"
    df.to_excel(out_file, index=False)
    print(f"\nSaved to: {out_file}")


if __name__ == "__main__":
    main()