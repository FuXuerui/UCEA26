import re
import time
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

# 先用已经确认存在的相关页面做 demo
URLS = [
    "https://www.alachuaschools.net/page/languageline",
    "https://www.alachuaschools.net/page/immigrantservices",
    "https://www.alachuaschools.net/page/esolcontacts",
    "https://www.alachuaschools.net/page/communicationplatforms",
]

# 不再要求完整短语完全一致，而是做更宽松的主题词匹配
TOPIC_PATTERNS = {
    "language_access": [
        r"\blanguage\s+line\b",
        r"\binterpreter\b",
        r"\binterpretation\b",
        r"\btranslation\b",
        r"\btranslator\b",
        r"\bmultilingual\b",
        r"\blanguage\b",
    ],
    "translation_services": [
        r"\btranslation services?\b",
        r"\binterpretation services?\b",
        r"\btranslator\b",
        r"\binterpreter\b",
        r"\blanguage line\b",
    ],
    "ell_parent_communication": [
        r"\bell\b",
        r"\besol\b",
        r"\benglish learners?\b",
        r"\bimmigrant family\b",
        r"\bparent\b",
        r"\bfamil(?:y|ies)\b",
        r"\bcommunication\b",
    ],
}

SCHOOL_PATTERN = re.compile(
    r"\b([A-Z][A-Za-z&'\\-]+(?:\s+[A-Z][A-Za-z&'\\-]+){0,6}\s+"
    r"(?:Elementary|Middle|High|School|Academy|Center))\b"
)

DATE_PATTERNS = [
    r"\b(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\.?\s+\d{1,2},\s+\d{4}\b",
    r"\b\d{1,2}/\d{1,2}/\d{2,4}\b",
    r"\b\d{4}-\d{2}-\d{2}\b",
]


def normalize_text(text: str) -> str:
    if not text:
        return ""
    return re.sub(r"\s+", " ", text).strip()


def get_html(url: str) -> str | None:
    try:
        resp = requests.get(url, headers=HEADERS, timeout=20)
        resp.raise_for_status()
        if "text/html" not in resp.headers.get("Content-Type", "").lower():
            return None
        return resp.text
    except Exception as e:
        print(f"[ERROR] {url} -> {e}")
        return None


def extract_title(soup: BeautifulSoup) -> str:
    if soup.title and soup.title.text.strip():
        return soup.title.text.strip()
    h1 = soup.find("h1")
    if h1:
        return normalize_text(h1.get_text(" ", strip=True))
    return ""


def extract_time(soup: BeautifulSoup) -> str:
    time_tag = soup.find("time")
    if time_tag:
        if time_tag.get("datetime"):
            return time_tag["datetime"].strip()
        txt = normalize_text(time_tag.get_text(" ", strip=True))
        if txt:
            return txt

    for attrs in [
        {"property": "article:published_time"},
        {"property": "article:modified_time"},
        {"property": "og:updated_time"},
        {"name": "date"},
        {"name": "publish_date"},
    ]:
        tag = soup.find("meta", attrs=attrs)
        if tag and tag.get("content"):
            return tag["content"].strip()

    text = normalize_text(soup.get_text(" ", strip=True))
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


def detect_topics(text: str) -> list[str]:
    text_low = text.lower()
    hits = []

    for topic, patterns in TOPIC_PATTERNS.items():
        for p in patterns:
            if re.search(p, text_low, flags=re.IGNORECASE):
                hits.append(topic)
                break

    return hits


def parse_page(url: str) -> dict | None:
    html = get_html(url)
    if not html:
        return None

    soup = BeautifulSoup(html, "lxml")
    text = normalize_text(soup.get_text(" ", strip=True))

    topic_hits = detect_topics(text)
    if not topic_hits:
        return None

    return {
        "url": url,
        "title": extract_title(soup),
        "topic_hits": "; ".join(topic_hits),
        "document_time": extract_time(soup),
        "school_name": extract_school_name(text),
    }


def main():
    rows = []

    for url in URLS:
        print(f"[CHECK] {url}")
        row = parse_page(url)
        if row:
            print(f"  -> HIT: {row['topic_hits']}")
            rows.append(row)
        else:
            print("  -> no hit")
        time.sleep(0.8)

    df = pd.DataFrame(rows)

    if df.empty:
        print("\nNo hits found.")
    else:
        print("\n=== RESULTS ===")
        print(df)
        df.to_excel("demo_known_pages_results.xlsx", index=False)
        print("\nSaved to: demo_known_pages_results.xlsx")


if __name__ == "__main__":
    main()