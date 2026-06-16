from __future__ import annotations

import html
import json
import re
from pathlib import Path
from typing import Any
from urllib.parse import quote
from urllib.request import Request, urlopen

import pdfplumber
from lxml import html as lxml_html


ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "assets"
OUT_JSON = ASSETS / "legal_ethics_articles.json"
SOURCE_ROOT = next(
    p for p in ROOT.parent.iterdir()
    if (p / "01_laws_lawgo").exists() and (p / "02_koreanbar_rules").exists()
)

SUBJECT = "법조윤리"
HEADERS = {"User-Agent": "Mozilla/5.0"}

LAW_TEXT_SOURCES = [
    ("변호사법", "01_*.txt", "https://www.law.go.kr/법령/변호사법"),
    ("외국법자문사법", "20_*.txt", "https://www.law.go.kr/법령/외국법자문사법"),
    ("민법", "21_*.txt", "https://www.law.go.kr/법령/민법"),
    ("행정소송법", "22_*.txt", "https://www.law.go.kr/법령/행정소송법"),
    ("공직선거법", "23_*.txt", "https://www.law.go.kr/법령/공직선거법"),
]

KOREANBAR_PDF_SOURCES = [
    ("대한변호사협회 회칙", "06_*.pdf"),
    ("변호사윤리장전", "07_*.pdf"),
    ("변호사 광고에 관한 규정", "08_*.pdf"),
    ("변호사 징계규칙", "09_*.pdf"),
]

REMOTE_HTML_SOURCES = [
    (
        "법관윤리강령",
        "https://www.law.go.kr/LSW/lsInfoR.do?lsiSeq=32976&chrClsCd=010202&efYd=19950701",
        "https://www.law.go.kr/LSW/lsInfoP.do?lsiSeq=32976",
    ),
    (
        "검사윤리강령",
        "https://www.law.go.kr/LSW/admRulLsInfoR.do?admRulSeq=2000000000845&joTpYn=Y&languageType=KO&chrClsCd=010202",
        "https://www.law.go.kr/LSW/admRulInfoP.do?admRulSeq=2000000000845",
    ),
]

LAW_ORDER = {
    name: idx
    for idx, name in enumerate(
        [
            "변호사법",
            "변호사윤리장전",
            "대한변호사협회 회칙",
            "변호사 징계규칙",
            "변호사 광고에 관한 규정",
            "외국법자문사법",
            "법관윤리강령",
            "검사윤리강령",
            "민법",
            "행정소송법",
            "공직선거법",
        ],
        1,
    )
}


def clean_text(value: str) -> str:
    value = html.unescape(value or "")
    value = value.replace("\xa0", " ").replace("\u3000", " ")
    value = value.replace("․", "ㆍ")
    value = re.sub(r"[ \t]+", " ", value)
    value = re.sub(r" *\n *", "\n", value)
    value = re.sub(r"\n{3,}", "\n\n", value)
    return value.strip()


def article_sort_key(article_no: str) -> tuple[int, int]:
    match = re.match(r"제(\d+)조(?:의(\d+))?$", article_no or "")
    if not match:
        return (9999, 9999)
    return (int(match.group(1)), int(match.group(2) or 0))


def article_code(article_no: str) -> str:
    base, sub = article_sort_key(article_no)
    return f"{base:04d}{sub:02d}"


def article_row(
    law_name: str,
    article_no: str,
    title: str,
    body: str,
    part: str | None,
    chapter: str | None,
    section: str | None,
    source: str,
    source_url: str,
) -> dict[str, Any]:
    sort_base, sort_sub = article_sort_key(article_no)
    return {
        "subject": SUBJECT,
        "law_name": law_name,
        "article_no": article_no,
        "article_code": article_code(article_no),
        "title": clean_text(title),
        "body": clean_text(body),
        "part": clean_text(part or ""),
        "chapter": clean_text(chapter or ""),
        "section": clean_text(section or ""),
        "source": source,
        "source_url": source_url,
        "sort_base": sort_base,
        "sort_sub": sort_sub,
    }


def normalize_heading(no: str, title: str, rest: str = "") -> str:
    title = clean_text(title)
    rest = clean_text(rest)
    heading = f"{no}({title})" if title else no
    return f"{heading} {rest}".strip()


def is_structure(line: str) -> tuple[str, str] | None:
    if re.match(r"^제\d+편\b", line):
        return ("part", line)
    if re.match(r"^제\d+장\b", line):
        return ("chapter", line)
    if re.match(r"^제\d+절\b", line):
        return ("section", line)
    return None


def is_supplementary_start(line: str) -> bool:
    return bool(re.match(r"^부\s*칙\b", line))


def text_article_match(line: str) -> re.Match[str] | None:
    match = re.match(r"^(제\d+조(?:의\d+)?)(?:\(([^)]*)\))?\s*(.*)$", line)
    if not match:
        return None
    if match.group(2) or re.match(r"^삭제\b", match.group(3) or ""):
        return match
    return None


def parse_law_text(law_name: str, path: Path, source_url: str) -> list[dict[str, Any]]:
    lines = [clean_text(line) for line in path.read_text(encoding="utf-8", errors="ignore").splitlines()]
    lines = [line for line in lines if line]
    rows: list[dict[str, Any]] = []
    part = chapter = section = ""
    current: dict[str, Any] | None = None
    body_lines: list[str] = []
    source = f"국가법령정보센터 {law_name}"

    def flush() -> None:
        nonlocal current, body_lines
        if not current:
            return
        body = clean_text("\n".join(body_lines))
        if body:
            rows.append(article_row(source=source, source_url=source_url, body=body, **current))
        current = None
        body_lines = []

    for line in lines:
        if is_supplementary_start(line):
            flush()
            break

        match = text_article_match(line)
        if match:
            flush()
            article_no, title, rest = match.group(1), match.group(2) or "", match.group(3) or ""
            current = {
                "law_name": law_name,
                "article_no": article_no,
                "title": title if title and title != "삭제" else "",
                "part": part,
                "chapter": chapter,
                "section": section,
            }
            body_lines = [normalize_heading(article_no, current["title"], rest)]
            continue

        structure = is_structure(line)
        if structure:
            flush()
            level, label = structure
            if level == "part":
                part, chapter, section = label, "", ""
            elif level == "chapter":
                chapter, section = label, ""
            else:
                section = label
            continue

        if current:
            body_lines.append(line)

    flush()
    return rows


def pdf_lines(path: Path) -> list[str]:
    with pdfplumber.open(str(path)) as pdf:
        text = "\n".join((page.extract_text() or "") for page in pdf.pages)
    lines = [clean_text(line) for line in text.splitlines()]
    skip = re.compile(
        r"^(\d+|20\d{2}\s+법규집.*|KOREAN BAR ASSOCIATION|대한변호사협회 회칙|회 칙|"
        r"변호사윤리장전|변호사 광고에 관한 규정|변호사징계규칙)$"
    )
    return [line for line in lines if line and not skip.match(line)]


def pdf_article_match(line: str) -> re.Match[str] | None:
    return re.match(r"^(제\d+조(?:의\d+)?)(?:\[(.*?)\]|\((.*?)\))\s*(.*)$", line)


def parse_koreanbar_pdf(law_name: str, path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    part = ""
    chapter = ""
    section = ""
    current: dict[str, Any] | None = None
    body_lines: list[str] = []
    source = "대한변호사협회 법규집"
    source_url = "https://www.koreanbar.or.kr/pages/board/law_list.asp"

    def flush() -> None:
        nonlocal current, body_lines
        if not current:
            return
        body = clean_text("\n".join(body_lines))
        if body:
            rows.append(article_row(source=source, source_url=source_url, body=body, **current))
        current = None
        body_lines = []

    for line in pdf_lines(path):
        if is_supplementary_start(line):
            flush()
            break

        match = pdf_article_match(line)
        if match:
            flush()
            article_no = match.group(1)
            title = match.group(2) or match.group(3) or ""
            rest = match.group(4) or ""
            current = {
                "law_name": law_name,
                "article_no": article_no,
                "title": title,
                "part": part,
                "chapter": chapter,
                "section": section,
            }
            body_lines = [normalize_heading(article_no, title, rest)]
            continue

        structure = is_structure(line)
        if structure:
            flush()
            level, label = structure
            if level == "part":
                part, chapter, section = label, "", ""
            elif level == "chapter":
                chapter, section = label, ""
            else:
                section = label
            continue

        if current:
            body_lines.append(line)

    flush()
    return rows


def fetch_text(url: str) -> str:
    request = Request(url, headers=HEADERS)
    with urlopen(request, timeout=40) as response:
        return response.read().decode("utf-8", errors="ignore")


def parse_lawgo_html(law_name: str, html_text: str, source_url: str) -> list[dict[str, Any]]:
    doc = lxml_html.fromstring(html_text)
    rows: list[dict[str, Any]] = []
    source = f"국가법령정보센터 {law_name}"

    for group in doc.xpath('//div[contains(concat(" ", normalize-space(@class), " "), " pgroup ")]'):
        lawcon = group.xpath('.//div[contains(concat(" ", normalize-space(@class), " "), " lawcon ")]')
        if not lawcon:
            continue
        label_nodes = lawcon[0].xpath('.//label')
        if not label_nodes:
            continue
        label_text = clean_text(label_nodes[0].text_content())
        match = re.match(r"^(제\d+조(?:의\d+)?)\s*(?:\((.*?)\))?$", label_text)
        if not match:
            continue
        article_no = match.group(1)
        title = match.group(2) or ""
        text = clean_text(lawcon[0].text_content())
        text = clean_text(text.replace(label_text, normalize_heading(article_no, title), 1))
        rows.append(
            article_row(
                law_name=law_name,
                article_no=article_no,
                title=title,
                body=text,
                part="",
                chapter="",
                section="",
                source=source,
                source_url=source_url,
            )
        )
    return rows


def load_all_rows() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    laws_dir = SOURCE_ROOT / "01_laws_lawgo"
    pdf_dir = SOURCE_ROOT / "02_koreanbar_rules"

    for law_name, pattern, source_url in LAW_TEXT_SOURCES:
        files = sorted(laws_dir.glob(pattern))
        if not files:
            raise FileNotFoundError(f"Missing law text source: {law_name} {pattern}")
        rows.extend(parse_law_text(law_name, files[0], source_url))

    for law_name, pattern in KOREANBAR_PDF_SOURCES:
        files = sorted(pdf_dir.glob(pattern))
        if not files:
            raise FileNotFoundError(f"Missing Korean Bar PDF source: {law_name} {pattern}")
        rows.extend(parse_koreanbar_pdf(law_name, files[0]))

    for law_name, fetch_url, source_url in REMOTE_HTML_SOURCES:
        rows.extend(parse_lawgo_html(law_name, fetch_text(fetch_url), source_url))

    rows.sort(key=lambda row: (LAW_ORDER.get(row["law_name"], 999), row["sort_base"], row["sort_sub"]))
    return rows


def main() -> None:
    rows = load_all_rows()
    counts: dict[str, int] = {}
    for row in rows:
        counts[row["law_name"]] = counts.get(row["law_name"], 0) + 1

    missing = [name for name in LAW_ORDER if not counts.get(name)]
    if missing:
        raise RuntimeError(f"Missing legal ethics article rows: {missing}")

    payload = {
        "updatedAt": "2026-06-17",
        "source": "법조윤리 법령자료 2026-06-16 및 국가법령정보센터",
        "items": rows,
    }
    ASSETS.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {OUT_JSON}")
    for name in LAW_ORDER:
        print(f"{name}: {counts.get(name, 0)}")
    print(f"total: {len(rows)}")


if __name__ == "__main__":
    main()
