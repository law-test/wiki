from __future__ import annotations

import html
import json
import os
import re
import time
from datetime import date
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, quote, urljoin, urlparse
from xml.etree import ElementTree as ET

import requests
from bs4 import BeautifulSoup


ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "assets"
ARTICLES_JSON = ASSETS / "commercial_law_articles.json"
COMMENTARIES_JSON = ASSETS / "commercial_law_commentaries.json"
RESOURCES_JSON = ASSETS / "commercial_law_resources.json"
CACHE_DIR = ROOT.parent / "law-test-private" / "commercial_law"
CASE_CACHE_JSON = CACHE_DIR / "case_cache.json"
KCI_CACHE_JSON = CACHE_DIR / "kci_keyword_cache.json"

LAW_NAME = "상법"
SUBJECT = "상법"
HEADERS = {"User-Agent": "Mozilla/5.0"}
MAX_CASES_PER_ARTICLE = int(os.environ.get("COMMERCIAL_MAX_CASES", "6"))
MAX_PAPERS_PER_ARTICLE = int(os.environ.get("COMMERCIAL_MAX_PAPERS", "4"))
REQUEST_SLEEP = float(os.environ.get("COMMERCIAL_REQUEST_SLEEP", "0.08"))
KCI_SLEEP = float(os.environ.get("COMMERCIAL_KCI_SLEEP", "0.18"))
ARTICLE_LIMIT = int(os.environ.get("COMMERCIAL_ARTICLE_LIMIT", "0") or "0")
SKIP_CASES = os.environ.get("COMMERCIAL_SKIP_CASES") == "1"
SKIP_KCI = os.environ.get("COMMERCIAL_SKIP_KCI") == "1"
KCI_KEY = os.environ.get("KCI_KEY", "")


def clean_text(value: str) -> str:
    value = html.unescape(value or "")
    value = value.replace("\xa0", " ").replace("\u3000", " ")
    value = re.sub(r"[ \t]+", " ", value)
    value = re.sub(r"\s*\n\s*", "\n", value)
    return value.strip()


def article_sort_key(article_no: str) -> tuple[int, int]:
    match = re.match(r"제(\d+)조(?:의(\d+))?$", article_no or "")
    if not match:
        return (9999, 9999)
    return (int(match.group(1)), int(match.group(2) or 0))


def article_code(article_no: str) -> str:
    base, sub = article_sort_key(article_no)
    return f"{base:04d}{sub:02d}"


def read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def law_iframe_params(law_name: str) -> dict[str, str]:
    url = "https://www.law.go.kr/%EB%B2%95%EB%A0%B9/" + quote(law_name)
    response = requests.get(url, headers=HEADERS, timeout=40)
    response.raise_for_status()
    match = re.search(r'src="([^"]*lsInfoP\.do[^"]+)"', response.text)
    if not match:
        raise RuntimeError(f"Cannot find law iframe for {law_name}")
    iframe = urljoin("https://www.law.go.kr", match.group(1).replace("&amp;", "&"))
    parsed = parse_qs(urlparse(iframe).query)
    return {key: value[0] for key, value in parsed.items()}


def fetch_law_html(law_name: str) -> tuple[str, dict[str, str]]:
    params = law_iframe_params(law_name)
    data = {
        "lsiSeq": params["lsiSeq"],
        "efYd": params["efYd"],
        "chrClsCd": "010202",
        "nwYn": "Y",
    }
    response = requests.post("https://www.law.go.kr/LSW/lsInfoR.do", data=data, headers=HEADERS, timeout=80)
    response.raise_for_status()
    return response.text, params


def normalize_structure_title(title: str) -> tuple[int, str] | None:
    title = clean_text(re.sub(r"<[^>]+>", " ", title))
    title = re.sub(r"\s*<[^>]*>\s*", " ", title).strip()
    title = re.sub(r"\s*<[^>]*$", "", title).strip()
    title = re.sub(r"\s*<[^>]*>", " ", title).strip()
    title = re.sub(r"\s*<[^>]*", "", title).strip()
    title = re.sub(r"\s*<[^>]*>", "", title).strip()
    title = re.sub(r"\s*<[^>]*$", "", title).strip()
    title = re.sub(r"\s*<[^>]*>", "", title)
    title = re.sub(r"\s*<[^>]*$", "", title)
    title = re.sub(r"\s*<[^>]*>", "", title)
    title = re.sub(r"\s*<[^>]*$", "", title)
    title = re.sub(r"\s*<[^>]*>", "", title)
    title = re.sub(r"\s*<[^>]*$", "", title)
    title = re.sub(r"\s*<[^>]*>", "", title)
    title = clean_text(re.sub(r"<[^>]*>", "", title))
    if not title.startswith("제"):
        return None
    if "편" in title:
        return (1, title)
    if "장" in title:
        return (2, title)
    if "절" in title:
        return (3, title)
    return None


def extract_articles(law_html: str, params: dict[str, str]) -> list[dict[str, Any]]:
    soup = BeautifulSoup(law_html, "html.parser")
    rows: list[dict[str, Any]] = []
    structure: list[str] = []
    source = f"국가법령정보센터 상법 시행 {params.get('efYd', '')}"
    source_url = "https://www.law.go.kr/%EB%B2%95%EB%A0%B9/" + quote(LAW_NAME)

    for node in soup.find_all(["p", "div"]):
        classes = node.get("class") or []
        if node.name == "p" and "gtit" in classes:
            parsed = normalize_structure_title(node.get_text(" ", strip=True))
            if parsed:
                level, title = parsed
                while len(structure) >= level:
                    structure.pop()
                structure.append(title)
            continue

        if node.name != "div" or "lawcon" not in classes:
            continue
        label = node.find("label")
        if not label:
            continue
        label_text = clean_text(label.get_text(" ", strip=True))
        match = re.match(r"(제\d+조(?:의\d+)?)(?:\((.*?)\))?$", label_text)
        if not match:
            continue
        article_no = match.group(1)
        title = clean_text(match.group(2) or "")
        paras = [clean_text(p.get_text(" ", strip=True)) for p in node.find_all("p")]
        body = clean_text("\n".join(p for p in paras if p))
        sort_base, sort_sub = article_sort_key(article_no)
        rows.append(
            {
                "subject": SUBJECT,
                "law_name": LAW_NAME,
                "article_no": article_no,
                "article_code": article_code(article_no),
                "title": title,
                "body": body,
                "part": structure[0] if len(structure) > 0 else "",
                "chapter": structure[1] if len(structure) > 1 else "",
                "section": structure[2] if len(structure) > 2 else "",
                "source": source,
                "source_url": source_url,
                "sort_base": sort_base,
                "sort_sub": sort_sub,
            }
        )
    return sorted(rows, key=lambda row: (row["sort_base"], row["sort_sub"]))


def category(row: dict[str, Any]) -> str:
    part = row.get("part") or ""
    chapter = row.get("chapter") or ""
    title = row.get("title") or ""
    text = " ".join([part, chapter, row.get("section") or "", title, row.get("body") or ""])
    if "회사" in part or any(word in chapter for word in ["회사", "합명회사", "합자회사", "유한책임회사", "주식회사", "유한회사", "외국회사", "벌칙"]):
        if any(word in text for word in ["주주", "주식", "주주총회", "이사", "감사", "신주", "사채"]):
            return "company_governance"
        return "company"
    if "보험" in part or "보험" in chapter or "보험" in title:
        return "insurance"
    if "해상" in part or "선박" in text or "운송" in chapter:
        return "maritime"
    if "항공" in part or "항공" in text:
        return "air"
    if "상행위" in part:
        if any(word in chapter for word in ["매매", "운송", "위탁", "중개", "창고", "금융리스", "가맹"]):
            return "commercial_transaction"
        return "commercial_act"
    if any(word in chapter for word in ["상인", "상업사용인", "상호", "상업장부", "상업등기", "영업양도"]):
        return "merchant"
    return "general"


CATEGORY_TEXT = {
    "general": {
        "purpose": "상사관계에 적용되는 기본 원칙과 민법과의 관계를 정리하는",
        "focus": "상법 총칙은 상거래에 민법보다 빠르고 강한 거래안전 규칙을 적용하기 위한 출발점이다. 상인, 상행위, 상사관습법, 민법 보충 적용의 순서를 구별해야 한다.",
        "practice": "사건에서는 먼저 당사자가 상인인지, 행위가 영업을 위한 것인지, 상법의 특칙이 민법보다 우선 적용되는지 확인한다.",
    },
    "merchant": {
        "purpose": "상인과 영업조직의 외부 표시ㆍ공시ㆍ이전 관계를 정리하는",
        "focus": "상인ㆍ상호ㆍ상업등기ㆍ영업양도 규정은 거래 상대방이 영업 주체와 책임 범위를 알 수 있게 하는 장치이다.",
        "practice": "실무에서는 등기 여부, 상호 사용, 영업양도 사실과 채권자 보호, 지배인 등 상업사용인의 대리권 범위를 함께 본다.",
    },
    "commercial_act": {
        "purpose": "상행위 일반에 적용되는 특칙을 정하는",
        "focus": "상행위 규정은 민법의 계약ㆍ채권 규정을 상거래 현실에 맞게 수정한다. 연대성, 보수청구, 이자, 소멸시효, 대리ㆍ위임 특칙이 중요하다.",
        "practice": "사건에서는 양쪽 모두 상인인지, 일방적 상행위인지, 행위가 영업을 위한 것인지에 따라 적용 조항과 효과가 달라진다.",
    },
    "commercial_transaction": {
        "purpose": "매매ㆍ운송ㆍ중개ㆍ위탁매매 등 영업상 거래유형별 기준을 정하는",
        "focus": "개별 상행위 규정은 거래 속도와 신뢰를 전제로 위험을 배분한다. 통지의무, 검사ㆍ하자통지, 운송인의 책임, 중개ㆍ위탁의 권리의무를 구별해야 한다.",
        "practice": "실무에서는 계약 유형, 목적물 인도와 검사 시점, 통지 기간, 운송장ㆍ창고증권 등 증권 발행 여부를 기록으로 확인한다.",
    },
    "company": {
        "purpose": "회사의 종류와 설립ㆍ조직ㆍ운영의 기본 구조를 정하는",
        "focus": "회사법 조문은 사단법리와 자본단체의 거래안전을 함께 조정한다. 회사 종류별 책임구조, 설립절차, 정관, 기관 구성을 구별해야 한다.",
        "practice": "실무에서는 정관, 등기, 주주 또는 사원의 지위, 기관 결의의 절차와 하자를 순서대로 확인한다.",
    },
    "company_governance": {
        "purpose": "주식회사와 회사기관의 권한ㆍ책임ㆍ자본거래를 정하는",
        "focus": "주식회사 규정에서는 주주평등, 자본충실, 이사의 충실의무와 선관주의의무, 주주총회ㆍ이사회 결의의 하자가 핵심이다.",
        "practice": "사건에서는 주식 보유관계, 의결권, 이사ㆍ감사의 권한, 결의 절차, 신주ㆍ사채 발행 목적과 공정성을 함께 본다.",
    },
    "insurance": {
        "purpose": "보험계약의 성립ㆍ효력ㆍ보험자의 책임과 보험계약자 측 의무를 정하는",
        "focus": "보험법은 위험단체의 공정성과 보험계약자 보호를 함께 다룬다. 고지의무, 위험변경, 보험사고, 보험자대위, 손해보험과 인보험의 차이가 중요하다.",
        "practice": "실무에서는 청약ㆍ승낙, 약관 설명, 고지사항, 사고 발생시점, 면책사유, 보험금 산정과 대위 범위를 순서대로 확인한다.",
    },
    "maritime": {
        "purpose": "선박ㆍ해상운송ㆍ해상위험에 관한 거래와 책임을 정하는",
        "focus": "해상법은 선박소유자, 운송인, 선장, 용선자, 적하 이해관계인의 위험분담을 정한다. 선하증권과 운송인의 책임제한이 자주 문제 된다.",
        "practice": "실무에서는 운송계약, 선적ㆍ양륙, 증권 문언, 사고 발생 해역과 원인, 책임제한 가능성을 확인한다.",
    },
    "air": {
        "purpose": "항공운송과 항공기 운항자의 책임을 정하는",
        "focus": "항공운송 규정은 국제운송규범과 연결되어 여객ㆍ수하물ㆍ화물 손해 및 제3자 손해의 책임범위를 정한다.",
        "practice": "실무에서는 운송구간, 사고 시점, 운송증권, 책임제한과 면책사유, 제척기간 또는 소멸시효를 확인한다.",
    },
}


def split_sentences(text: str) -> list[str]:
    text = clean_text(text)
    return [part.strip() for part in re.split(r"(?<=[.다])\s+", text) if part.strip()]


def make_commentary(row: dict[str, Any]) -> dict[str, Any]:
    info = CATEGORY_TEXT[category(row)]
    article_no = row.get("article_no") or ""
    title = row.get("title") or article_no
    context = " · ".join(x for x in [row.get("part"), row.get("chapter"), row.get("section")] if x)
    first_sentence = split_sentences(row.get("body") or "")
    quoted = first_sentence[0] if first_sentence else ""
    if len(quoted) > 170:
        quoted = quoted[:167].rstrip() + "..."
    return {
        "subject": SUBJECT,
        "law_name": LAW_NAME,
        "article_no": article_no,
        "title": title,
        "gist": f"{title}에 관하여 {info['purpose']} 조문이다.",
        "source_note": "국가법령정보센터 상법 조문 체계를 바탕으로 공개용으로 재서술한 요약입니다.",
        "manual_topics": [x for x in [row.get("part"), row.get("chapter"), row.get("section")] if x][:3],
        "explanations": [
            {
                "title": "1. 조문의 기능",
                "paragraphs": [
                    f"{article_no}는 {context or '상법'} 부분에서 {title}을 정한다. {quoted}",
                    "상법은 민법의 특별법으로 작동하는 경우가 많으므로, 해당 조문이 상인ㆍ상행위ㆍ회사ㆍ보험ㆍ운송 중 어느 장면에 붙는지 먼저 보아야 한다.",
                ],
            },
            {
                "title": "2. 실무상 확인할 점",
                "paragraphs": [
                    info["focus"],
                    info["practice"],
                ],
            },
        ],
    }


def parse_case_title(text: str) -> dict[str, str]:
    text = clean_text(re.sub(r"^\d+\.\s*", "", text))
    meta_match = re.search(r"\[([^\]]+?)\]\s*$", text)
    court = decision_date = case_no = ""
    if meta_match:
        meta = meta_match.group(1)
        title = clean_text(text[: meta_match.start()])
        parts = meta.split()
        if parts:
            court = parts[0]
        date_match = re.search(r"(\d{4}\.\s*\d{1,2}\.\s*\d{1,2}\.)", meta)
        if date_match:
            decision_date = clean_text(date_match.group(1))
        case_match = re.search(r"((?:\d{4})?[가-힣]{1,4}\d+(?:-\d+)?)", meta)
        if case_match:
            case_no = case_match.group(1)
    else:
        title = text
    return {"title": title, "court": court, "decision_date": decision_date, "case_no": case_no}


def search_cases(article: dict[str, Any]) -> list[dict[str, Any]]:
    query = f"{LAW_NAME} {article['article_no']}"
    params = {
        "q": query,
        "section": "bdyText",
        "outmax": str(MAX_CASES_PER_ARTICLE),
        "pg": "1",
        "p1": "",
        "p2": "",
        "p3": "",
        "d1": "",
        "d2": "",
        "dsort": "",
        "fsort": "21,10,30",
        "csq": "",
        "precSeq": "0",
        "dtlYn": "N",
    }
    url = "https://www.law.go.kr/LSW/precScListR.do?menuId=7&subMenuId=47&tabMenuId=213"
    response = requests.post(url, data=params, headers=HEADERS, timeout=45)
    response.raise_for_status()
    soup = BeautifulSoup(response.text, "html.parser")
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for anchor in soup.find_all("a"):
        onclick = anchor.get("onclick") or ""
        match = re.search(r"precView\('(\d+)'\)", onclick)
        if not match:
            continue
        case_id = match.group(1)
        if case_id in seen:
            continue
        seen.add(case_id)
        parsed = parse_case_title(anchor.get_text(" ", strip=True))
        rank = len(out) + 1
        title = parsed["title"] or parsed["case_no"] or "판례"
        out.append(
            {
                "case_id": case_id,
                "title": title,
                "court": parsed["court"],
                "decision_date": parsed["decision_date"],
                "case_no": parsed["case_no"],
                "url": f"https://www.law.go.kr/LSW/precInfoP.do?precSeq={case_id}",
                "source": "국가법령정보센터 판례검색",
                "rank": rank,
                "query": query,
                "summary": f"「{title}」 사건에서 {query}와 관련된 상사법 쟁점을 확인할 수 있습니다.",
            }
        )
    return out


def keyword_candidates(article: dict[str, Any]) -> list[str]:
    title = re.sub(r"[（(].*?[）)]", "", article.get("title") or "")
    title = title.replace("ㆍ", " ").replace("-", " ")
    chapter = re.sub(r"^제\d+(?:장의\d+)?장\s*", "", article.get("chapter") or "")
    section = re.sub(r"^제\d+절\s*", "", article.get("section") or "")
    extras = {
        "상사적용법규": ["상사관습법", "상법 적용"],
        "일방적 상행위": ["일방적 상행위"],
        "상인": ["상인개념", "상인"],
        "상업등기": ["상업등기"],
        "영업양도": ["영업양도"],
        "상사시효": ["상사소멸시효"],
        "이사의 의무": ["이사의 충실의무", "이사의 선관주의의무"],
        "주주총회": ["주주총회"],
        "신주발행": ["신주발행"],
        "보험자대위": ["보험자대위"],
        "고지의무": ["보험 고지의무"],
        "운송인의 손해배상책임": ["운송인의 책임"],
        "선하증권": ["선하증권"],
    }
    words = [title, chapter, section]
    for key, values in extras.items():
        if key in title or key in chapter or key in section:
            words.extend(values)
    cleaned: list[str] = []
    for word in words:
        word = clean_text(word)
        if 2 <= len(word) <= 24 and word not in cleaned and "삭제" not in word:
            cleaned.append(word)
    return cleaned[:3]


def kci_search(keyword: str) -> list[dict[str, Any]]:
    if not KCI_KEY or len(keyword) < 2:
        return []
    url = "https://apis.data.go.kr/B552540/KCIOpenApi/artiInfo/openApiM310List"
    params = {
        "serviceKey": KCI_KEY,
        "pageNo": "1",
        "recordCnt": "20",
        "artiNm": keyword,
    }
    response = requests.get(url, params=params, timeout=22)
    response.raise_for_status()
    root = ET.fromstring(response.content)
    rows: list[dict[str, Any]] = []
    for item in root.findall(".//item"):
        get = lambda tag: clean_text(item.findtext(tag) or "")
        paper_id = get("ARTI_ID")
        title = get("ARTI_KOR_TITL") or get("ARTI_FOLA_TITL") or get("ARTI_ENG_TITL")
        if not paper_id or not title:
            continue
        field = get("STUD_FIEL_CD")
        if field and not field.startswith("B13"):
            continue
        year = (get("RESI_DT") or get("ORTE_RESI_DT") or get("UPDATE_DT"))[:4]
        rows.append(
            {
                "paper_id": paper_id,
                "title": title,
                "author": get("AUTR_NM"),
                "journal": get("SERE_NM"),
                "year": year,
                "keywords": get("KOR_KEYW"),
                "uci": get("UCI"),
                "oa": get("ORTE_YN"),
                "source": "KCI Open API",
                "summary": f"「{title}」은(는) {keyword}와 관련된 상사법 쟁점을 다룬 논문입니다.",
            }
        )
    return rows


def build_resources(articles: list[dict[str, Any]]) -> dict[str, Any]:
    case_cache: dict[str, list[dict[str, Any]]] = read_json(CASE_CACHE_JSON, {})
    kci_cache: dict[str, list[dict[str, Any]]] = read_json(KCI_CACHE_JSON, {})
    resource_articles: dict[str, dict[str, list[dict[str, Any]]]] = {}
    work_articles = articles[:ARTICLE_LIMIT] if ARTICLE_LIMIT else articles

    for idx, article in enumerate(work_articles, 1):
        article_no = article["article_no"]
        entry = {"cases": [], "papers": []}
        if not SKIP_CASES:
            if article_no not in case_cache:
                try:
                    case_cache[article_no] = search_cases(article)
                except Exception as exc:
                    print(f"case search failed {article_no}: {exc}", flush=True)
                    case_cache[article_no] = []
                write_json(CASE_CACHE_JSON, case_cache)
                time.sleep(REQUEST_SLEEP)
            entry["cases"] = case_cache.get(article_no, [])

        if KCI_KEY or kci_cache:
            seen_papers: set[str] = set()
            for keyword in keyword_candidates(article):
                if keyword not in kci_cache:
                    if SKIP_KCI or not KCI_KEY:
                        continue
                    try:
                        kci_cache[keyword] = kci_search(keyword)
                    except Exception as exc:
                        print(f"KCI search failed {keyword}: {exc}", flush=True)
                        kci_cache[keyword] = []
                    write_json(KCI_CACHE_JSON, kci_cache)
                    time.sleep(KCI_SLEEP)
                for paper in kci_cache.get(keyword, []):
                    if len(entry["papers"]) >= MAX_PAPERS_PER_ARTICLE:
                        break
                    if paper["paper_id"] in seen_papers:
                        continue
                    seen_papers.add(paper["paper_id"])
                    p = dict(paper)
                    p["keyword"] = keyword
                    p["rank"] = len(entry["papers"]) + 1
                    entry["papers"].append(p)

        resource_articles[article_no] = entry
        if idx % 50 == 0:
            print(f"resources {idx}/{len(work_articles)}", flush=True)

    return {
        "updatedAt": date.today().isoformat(),
        "source": "국가법령정보센터 판례검색 및 KCI Open API 기반 상법 조문 연결 자료",
        "articles": resource_articles,
    }


def main() -> None:
    law_html, params = fetch_law_html(LAW_NAME)
    articles = extract_articles(law_html, params)
    write_json(
        ARTICLES_JSON,
        {
            "updatedAt": date.today().isoformat(),
            "source": f"국가법령정보센터 상법 시행 {params.get('efYd', '')}",
            "items": articles,
        },
    )
    write_json(
        COMMENTARIES_JSON,
        {
            "updatedAt": date.today().isoformat(),
            "source": "상법 전 조문 공개용 해설 초안",
            "items": [make_commentary(article) for article in articles],
        },
    )
    resources = build_resources(articles)
    write_json(RESOURCES_JSON, resources)
    print(
        f"wrote articles={len(articles)} commentaries={len(articles)} "
        f"resource_articles={len(resources['articles'])}",
        flush=True,
    )


if __name__ == "__main__":
    main()
