from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any
from urllib.parse import quote, urljoin, urlparse, parse_qs

import requests
from bs4 import BeautifulSoup


ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT.parent / "law-test-private" / "public_criminal_laws"
ARTICLES_JSON = OUT_DIR / "law_subject_articles.json"
SQL_OUT = OUT_DIR / "supabase_law_subject_articles.sql"
SQL_ASCII_OUT = OUT_DIR / "supabase_law_subject_articles_ascii.sql"

LAW_GROUPS = [
    {"subject": "형법", "law_name": "형법"},
    {"subject": "형사소송법", "law_name": "형사소송법"},
    {"subject": "헌법", "law_name": "대한민국헌법"},
    {"subject": "행정법", "law_name": "행정기본법"},
    {"subject": "행정법", "law_name": "행정절차법"},
    {"subject": "행정법", "law_name": "행정소송법"},
]

HEADERS = {"User-Agent": "Mozilla/5.0"}


def clean_text(value: str) -> str:
    value = re.sub(r"\s+", " ", value or "").strip()
    return value


def article_sort_key(article_no: str) -> tuple[int, int]:
    m = re.match(r"제(\d+)조(?:의(\d+))?$", article_no)
    if not m:
        return (9999, 9999)
    return (int(m.group(1)), int(m.group(2) or 0))


def article_code(article_no: str) -> str:
    base, sub = article_sort_key(article_no)
    return f"{base:04d}{sub:02d}"


def law_iframe_params(law_name: str) -> dict[str, str]:
    url = "https://www.law.go.kr/법령/" + quote(law_name)
    r = requests.get(url, headers=HEADERS, timeout=30)
    r.raise_for_status()
    m = re.search(r'src="([^"]*lsInfoP\.do[^"]+)"', r.text)
    if not m:
        raise RuntimeError(f"Cannot find law iframe for {law_name}")
    iframe = urljoin("https://www.law.go.kr", m.group(1).replace("&amp;", "&"))
    qs = parse_qs(urlparse(iframe).query)
    return {k: v[0] for k, v in qs.items()}


def fetch_law_html(law_name: str) -> tuple[str, dict[str, str]]:
    params = law_iframe_params(law_name)
    data = {
        "lsiSeq": params["lsiSeq"],
        "efYd": params["efYd"],
        "chrClsCd": "010202",
        "nwYn": "Y",
    }
    r = requests.post("https://www.law.go.kr/LSW/lsInfoR.do", data=data, headers=HEADERS, timeout=60)
    r.raise_for_status()
    return r.text, params


def extract_articles(subject: str, law_name: str, law_html: str, params: dict[str, str]) -> list[dict[str, Any]]:
    soup = BeautifulSoup(law_html, "html.parser")
    rows: list[dict[str, Any]] = []
    structure: list[str] = []
    source = f"국가법령정보센터 {law_name}(시행 {params.get('efYd', '')})"
    source_url = "https://www.law.go.kr/법령/" + quote(law_name)

    for node in soup.find_all(["p", "div"]):
        cls = node.get("class") or []
        if node.name == "p" and "gtit" in cls:
            title = clean_text(node.get_text(" ", strip=True))
            if title.startswith("제") or title in {"전문", "부칙"}:
                level = 1
                if "편" in title:
                    level = 1
                elif "장" in title:
                    level = 2
                elif "절" in title:
                    level = 3
                while len(structure) >= level:
                    structure.pop()
                structure.append(title)
            continue

        if node.name != "div" or "lawcon" not in cls:
            continue
        label = node.find("label")
        if not label:
            continue
        label_text = clean_text(label.get_text(" ", strip=True))
        m = re.match(r"(제\d+조(?:의\d+)?)(?:\((.*?)\))?$", label_text)
        if not m:
            continue
        no = m.group(1)
        title = clean_text(m.group(2) or "")
        paras = [clean_text(p.get_text(" ", strip=True)) for p in node.find_all("p")]
        body = clean_text("\n".join(p for p in paras if p))
        sort_base, sort_sub = article_sort_key(no)
        rows.append(
            {
                "id": f"{subject}:{law_name}:{no}",
                "subject": subject,
                "law_name": law_name,
                "article_no": no,
                "article_code": article_code(no),
                "title": title,
                "body": body,
                "part": structure[0] if len(structure) > 0 else None,
                "chapter": structure[1] if len(structure) > 1 else None,
                "section": structure[2] if len(structure) > 2 else None,
                "source": source,
                "source_url": source_url,
                "sort_base": sort_base,
                "sort_sub": sort_sub,
            }
        )
    return rows


def sql_quote(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, (int, float)):
        return str(value)
    return "'" + str(value).replace("'", "''") + "'"


def ascii_sql_literal(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, (int, float)):
        return str(value)
    escaped = str(value).replace("\\", "\\\\").replace("'", "''")
    return "convert_from(decode('" + escaped.encode("utf-8").hex() + "','hex'),'UTF8')"


def build_sql(rows: list[dict[str, Any]], ascii_only: bool = False) -> str:
    lit = ascii_sql_literal if ascii_only else sql_quote
    cols = [
        "id",
        "subject",
        "law_name",
        "article_no",
        "article_code",
        "title",
        "body",
        "part",
        "chapter",
        "section",
        "source",
        "source_url",
        "sort_base",
        "sort_sub",
    ]
    values = []
    for row in rows:
        values.append("(" + ", ".join(lit(row.get(col)) for col in cols) + ")")

    subjects = ["형법", "형사소송법", "헌법", "행정법"]
    subject_list = ", ".join(lit(subject) for subject in subjects)

    return f"""create table if not exists public.law_subject_articles (
  id text primary key,
  subject text not null,
  law_name text not null,
  article_no text not null,
  article_code text not null,
  title text not null,
  body text not null,
  part text,
  chapter text,
  section text,
  source text,
  source_url text,
  sort_base integer,
  sort_sub integer,
  created_at timestamptz default now()
);

alter table public.law_subject_articles enable row level security;

drop policy if exists "law subject articles readable" on public.law_subject_articles;
create policy "law subject articles readable"
on public.law_subject_articles for select
using (true);

grant usage on schema public to anon, authenticated;
grant select on public.law_subject_articles to anon, authenticated;

delete from public.law_subject_articles
where subject in ({subject_list});

insert into public.law_subject_articles
  ({", ".join(cols)})
values
{",\n".join(values)}
on conflict (id) do update set
  subject = excluded.subject,
  law_name = excluded.law_name,
  article_no = excluded.article_no,
  article_code = excluded.article_code,
  title = excluded.title,
  body = excluded.body,
  part = excluded.part,
  chapter = excluded.chapter,
  section = excluded.section,
  source = excluded.source,
  source_url = excluded.source_url,
  sort_base = excluded.sort_base,
  sort_sub = excluded.sort_sub;
"""


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    all_rows: list[dict[str, Any]] = []
    for cfg in LAW_GROUPS:
        html, params = fetch_law_html(cfg["law_name"])
        rows = extract_articles(cfg["subject"], cfg["law_name"], html, params)
        print(f"{cfg['subject']} / {cfg['law_name']}: {len(rows)} articles")
        all_rows.extend(rows)

    ARTICLES_JSON.write_text(json.dumps(all_rows, ensure_ascii=False, indent=2), encoding="utf-8")
    SQL_OUT.write_text(build_sql(all_rows), encoding="utf-8")
    SQL_ASCII_OUT.write_text(build_sql(all_rows, ascii_only=True), encoding="ascii")
    print(f"wrote {len(all_rows)} rows")
    print(SQL_ASCII_OUT)


if __name__ == "__main__":
    main()
