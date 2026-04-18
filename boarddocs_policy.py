import re
import time
import pandas as pd
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError

URLS = [
    "https://go.boarddocs.com/fl/alaco/Board.nsf/Public",
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


def safe_inner_text(locator):
    try:
        return locator.inner_text(timeout=5000)
    except:
        return ""


def collect_page_text(page) -> str:
    """
    尽可能从 page 和所有 frame 中提取文本
    """
    chunks = []

    # 主页面 body
    try:
        body_text = safe_inner_text(page.locator("body"))
        if body_text:
            chunks.append(body_text)
    except:
        pass

    # 所有 frame
    for i, frame in enumerate(page.frames):
        try:
            txt = frame.locator("body").inner_text(timeout=5000)
            txt = normalize_text(txt)
            if txt:
                chunks.append(f"[FRAME_{i}] {txt}")
        except:
            continue

    return normalize_text("\n".join(chunks))


def collect_links_and_buttons(page) -> str:
    """
    抓取所有链接 / 按钮 / 菜单项等可见文字，BoardDocs 这类站点常常正文很碎，
    所以把控件文字一起抓下来有助于后续分析
    """
    chunks = []

    selectors = [
        "a",
        "button",
        "[role='button']",
        "[role='treeitem']",
        "[role='menuitem']",
        "[onclick]",
        "li",
        "span",
        "div",
    ]

    # 主页面
    for sel in selectors:
        try:
            loc = page.locator(sel)
            n = min(loc.count(), 300)
            for i in range(n):
                try:
                    txt = normalize_text(loc.nth(i).inner_text(timeout=1500))
                    if txt and len(txt) >= 2:
                        chunks.append(txt)
                except:
                    continue
        except:
            continue

    # 各个 frame
    for frame in page.frames:
        for sel in selectors:
            try:
                loc = frame.locator(sel)
                n = min(loc.count(), 300)
                for i in range(n):
                    try:
                        txt = normalize_text(loc.nth(i).inner_text(timeout=1500))
                        if txt and len(txt) >= 2:
                            chunks.append(txt)
                    except:
                        continue
            except:
                continue

    # 去重但保留顺序
    chunks = list(dict.fromkeys(chunks))
    return normalize_text("\n".join(chunks))


def click_section_if_possible(page, target_texts):
    for txt in target_texts:
        try:
            page.get_by_text(txt, exact=False).first.click(timeout=5000)
            page.wait_for_timeout(3000)
            return f"clicked:{txt}"
        except:
            continue

    for frame in page.frames:
        for txt in target_texts:
            try:
                frame.get_by_text(txt, exact=False).first.click(timeout=5000)
                page.wait_for_timeout(3000)
                return f"clicked_in_frame:{txt}"
            except:
                continue

    return "not_clicked"

def try_expand_elements(page, max_clicks=20):
    """
    尝试点击一些可能是 agenda item / 展开按钮的元素
    注意：这里只做温和点击，不做激进遍历，避免页面崩
    """
    clicked = 0
    click_log = []

    selectors = [
        "a",
        "button",
        "[role='button']",
        "[role='treeitem']",
    ]

    target_words = [
        "agenda",
        "meeting",
        "item",
        "minutes",
        "attachments",
        "view",
        "details",
        "more",
    ]

    # 先主页面，再 frame
    contexts = [("page", page)] + [(f"frame_{i}", fr) for i, fr in enumerate(page.frames)]

    for ctx_name, ctx in contexts:
        for sel in selectors:
            try:
                loc = ctx.locator(sel)
                n = min(loc.count(), 80)
                for i in range(n):
                    if clicked >= max_clicks:
                        return click_log

                    try:
                        elem = loc.nth(i)
                        txt = normalize_text(elem.inner_text(timeout=1000)).lower()
                        if not txt:
                            continue

                        if any(w in txt for w in target_words):
                            elem.click(timeout=2000)
                            page.wait_for_timeout(1500)
                            clicked += 1
                            click_log.append(f"{ctx_name}:{sel}:{txt[:80]}")
                    except:
                        continue
            except:
                continue

    return click_log


def get_boarddocs_data(page, url: str) -> dict:
    try:
        page.goto(url, wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(5000)

        title = page.title()

        section_click_status = click_section_if_possible(page, ["Policies", "Policy"])
        click_log = try_expand_elements(page, max_clicks=15)

        raw_text_1 = collect_page_text(page)
        raw_text_2 = collect_links_and_buttons(page)

        full_text = normalize_text(raw_text_1 + "\n" + raw_text_2)

        hits = find_hits(full_text, KEYWORDS)
        doc_time = extract_date(full_text)
        school_name = extract_school_name(full_text)

        return {
            "url": url,
            "title": title,
            "section_click_status": section_click_status,
            "clicked_elements": " | ".join(click_log[:30]),
            "matched_keywords": "; ".join(hits),
            "document_time": doc_time,
            "school_name": school_name,
            "text_preview": full_text[:3000],
            "text_length": len(full_text),
            "status": "ok",
        }

    except PlaywrightTimeoutError as e:
        return {
            "url": url,
            "title": "",
            "meeting_click_status": "",
            "clicked_elements": "",
            "matched_keywords": "",
            "document_time": "",
            "school_name": "",
            "text_preview": "",
            "text_length": 0,
            "status": f"timeout_error: {e}",
        }
    except Exception as e:
        return {
            "url": url,
            "title": "",
            "meeting_click_status": "",
            "clicked_elements": "",
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

        context = browser.new_context()
        page = context.new_page()

        for url in URLS:
            print(f"[CHECK] {url}")
            row = get_boarddocs_data(page, url)
            print(f"  -> {row['status']}")
            print(f"     title = {row['title']}")
            print(f"     section_click_status = {row['section_click_status']}")
            print(f"     text_length = {row['text_length']}")
            if row["matched_keywords"]:
                print(f"     HIT: {row['matched_keywords']}")
            if row["clicked_elements"]:
                print(f"     CLICKED: {row['clicked_elements'][:300]}")
            rows.append(row)
            time.sleep(1)

        browser.close()

    df = pd.DataFrame(rows)
    out_file = "boarddocs_policy_results.xlsx"
    df.to_excel(out_file, index=False)
    print(f"\nSaved to: {out_file}")


if __name__ == "__main__":
    main()