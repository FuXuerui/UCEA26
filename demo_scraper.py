import re
import time
from urllib.parse import quote, urljoin

import requests
import pandas as pd
from bs4 import BeautifulSoup

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    )
}

KEYWORDS = [
    "language access policy",
    "translation services",
    "ELL parent communication",
]

DOMAIN_FILTER = "alachuaschools.net"


def normalize_text(text: str) -> str:
    if not text:
        return ""
    return re.sub(r"\s+", " ", text).strip()


def get_html(url: str) -> str | None:
    try:
        resp = requests.get(url, headers=HEADERS, timeout=20)
        resp.raise_for_status()
        return resp.text
    except Exception as e:
        print(f"[ERROR] {url} -> {e}")
        return None


def search_bing(query: str, max_results: int = 10) -> list[str]:
    """
    用 Bing 搜索站内页面
    """
    search_url = f"https://www.bing.com/search?q={quote(query)}"
    html = get_html(search_url)
    if not html:
        return []

    soup = BeautifulSoup(html, "lxml")
    links = []

    for a in soup.select("li.b_algo h2 a"):
        href = a.get("href", "").strip()
        if DOMAIN_FILTER in href:
            links.append(href)

    # 去重
    deduped = list(dict.fromkeys(links))
    return deduped[:max_results]


def extract_title(soup: BeautifulSoup) -> str:
    if soup.title and soup.title.text.strip():
        return soup.title.text.strip()
    h1 = soup.find("h1")
    if h1:
        return normalize_text(h1.get_text(" ", strip=True))
    return ""


def extract_page_time(soup: BeautifulSoup) -> str:
    time_tag = soup.find("time")
    if time_tag:
        if time_tag.get("datetime"):
            return time_tag["datetime"].strip()
        txt = normalize_text(time_tag.get_text(" ", strip=True))
        if txt:
            return txt

    meta_candidates = [
        {"property": "article:published_time"},
        {"property": "article:modified_time"},
        {"property": "og:updated_time"},
        {"name": "date"},
        {"name": "publish_date"},
    ]
    for attrs in meta_candidates:
        tag = soup.find("meta", attrs=attrs)
        if tag and tag.get("content"):
            return tag["content"].strip()

    text = normalize_text(soup.get_text(" ", strip=True))
    patterns = [
        r"\b(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\.?\s+\d{1,2},\s+\d{4}\b",
        r"\b\d{1,2}/\d{1,2}/\d{2,4}\b",
        r"\b\d{4}-\d{2}-\d{2}\b",
    ]
    for p in patterns:
        m = re.search(p, text, flags=re.IGNORECASE)
        if m:
            return m.group(0)

    return ""


def extract_school_name(text: str) -> str:
    pattern = re.compile(
        r"\b([A-Z][A-Za-z&'\-]+(?:\s+[A-Z][A-Za-z&'\-]+){0,6}\s+"
        r"(?:Elementary|Middle|High|School|Academy|Center))\b"
    )
    matches = pattern.findall(text)
    if matches:
        return list(dict.fromkeys(matches))[0]
    return ""


def find_keyword_hits(text: str, keywords: list[str]) -> list[str]:
    text_low = text.lower()
    hits = []
    for kw in keywords:
        if kw.lower() in text_low:
            hits.append(kw)
    return hits


def parse_page(url: str, source_keyword: str) -> dict | None:
    html = get_html(url)
    if not html:
        return None

    soup = BeautifulSoup(html, "lxml")
    text = normalize_text(soup.get_text(" ", strip=True))

    hits = find_keyword_hits(text, KEYWORDS)
    if not hits:
        return None

    return {
        "search_keyword": source_keyword,
        "url": url,
        "title": extract_title(soup),
        "matched_keywords": "; ".join(hits),
        "document_time": extract_page_time(soup),
        "school_name": extract_school_name(text),
    }


def main():
    all_candidate_links = []

    for kw in KEYWORDS:
        query = f'site:{DOMAIN_FILTER} "{kw}"'
        print(f"\n[SEARCH] {query}")
        links = search_bing(query, max_results=10)

        for link in links:
            all_candidate_links.append((kw, link))
            print(f"  {link}")

        time.sleep(1)

    # 去重 URL
    seen = set()
    deduped_candidates = []
    for kw, link in all_candidate_links:
        if link not in seen:
            seen.add(link)
            deduped_candidates.append((kw, link))

    rows = []
    for kw, link in deduped_candidates:
        print(f"\n[CHECK] {link}")
        row = parse_page(link, kw)
        if row:
            print(f"  -> HIT: {row['matched_keywords']}")
            rows.append(row)
        time.sleep(0.8)

    df = pd.DataFrame(rows)

    if df.empty:
        print("\nNo validated hits found.")
    else:
        df = df.drop_duplicates(subset=["url"]).reset_index(drop=True)
        print("\n=== RESULTS ===")
        print(df)
        df.to_excel("demo_search_results.xlsx", index=False)
        print("\nSaved to: demo_search_results.xlsx")


if __name__ == "__main__":
    main()