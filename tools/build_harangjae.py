from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable
from xml.etree import ElementTree as ET
from zipfile import ZipFile


ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "assets"
PRIVATE_DIR = Path("C:/cowork/harangjae_private")
HWPX_HINTS = ("202603", "무지개", "민법2")


def find_hwpx() -> Path:
    docs = Path.home() / "Documents"
    matches = []
    for path in docs.rglob("*.hwpx"):
        if any(hint in path.name for hint in HWPX_HINTS):
            matches.append(path)
    if not matches:
        raise FileNotFoundError("민법 II 강의안 HWPX 파일을 찾지 못했습니다.")
    return max(matches, key=lambda p: p.stat().st_size)


def extract_paragraphs(path: Path) -> list[str]:
    ns = {"hp": "http://www.hancom.co.kr/hwpml/2011/paragraph"}
    paras: list[str] = []
    with ZipFile(path) as archive:
        sections = sorted(
            name
            for name in archive.namelist()
            if name.startswith("Contents/section") and name.endswith(".xml")
        )
        for name in sections:
            root = ET.fromstring(archive.read(name))
            for para in root.findall(".//hp:p", ns):
                text = "".join((node.text or "") for node in para.findall(".//hp:t", ns))
                text = re.sub(r"\s+", " ", text).strip()
                if text:
                    paras.append(text)
    return paras


def article_range(start: int, end: int) -> list[str]:
    return [f"제{i}조" for i in range(start, end + 1)]


def first_index(paras: list[str], *needles: str, start_at: int = 0) -> int:
    for needle in needles:
        for idx, text in enumerate(paras[start_at:], start_at):
            if needle in text:
                return idx
    return -1


def next_index(paras: list[str], start: int, needles: Iterable[str]) -> int:
    if start < 0:
        return -1
    for idx in range(start + 1, len(paras)):
        if any(needle in paras[idx] for needle in needles):
            return idx
    return len(paras)


def clean_point(text: str) -> str:
    text = re.sub(r"^[*=▷⇒\-\s]+", "", text).strip()
    text = re.sub(r"^□\s*", "", text).strip()
    return text


def pick_points(paras: list[str], start_needle: str, stop_needles: Iterable[str], limit: int = 6) -> list[str]:
    start = first_index(paras, start_needle, start_at=88)
    stop = next_index(paras, start, stop_needles)
    if start < 0 or stop < 0:
        return []
    out: list[str] = []
    for text in paras[start + 1 : stop]:
        raw = text.strip()
        if len(raw) < 12 or len(raw) > 230:
            continue
        if raw.startswith("대법원 "):
            continue
        good = (
            raw.startswith(("*", "□", "<판례>", "=", "⇒", "cf.", "▷"))
            or re.match(r"^\(?\d+\)", raw)
            or re.match(r"^[가-하]\.", raw)
        )
        if not good:
            continue
        point = clean_point(raw)
        if point and point not in out:
            out.append(point)
        if len(out) >= limit:
            break
    return out


def pick_cases(paras: list[str], start_needle: str, stop_needles: Iterable[str], limit: int = 3) -> list[str]:
    start = first_index(paras, start_needle, start_at=88)
    stop = next_index(paras, start, stop_needles)
    if start < 0 or stop < 0:
        return []
    cases: list[str] = []
    for idx, text in enumerate(paras[start + 1 : stop], start + 1):
        if not text.startswith("<판례>"):
            continue
        title = clean_point(text.replace("<판례>", ""))
        court = ""
        for nxt in paras[idx + 1 : min(idx + 8, stop)]:
            if nxt.startswith("대법원 "):
                court = nxt
                break
        item = f"{title} - {court}" if court else title
        if item not in cases:
            cases.append(item)
        if len(cases) >= limit:
            break
    return cases


def make_note(
    paras: list[str],
    note_id: str,
    title: str,
    lecture: str,
    articles: list[str],
    summary: str,
    start: str,
    stop: Iterable[str],
    limit: int = 6,
) -> dict:
    return {
        "id": note_id,
        "title": title,
        "lecture": lecture,
        "articles": articles,
        "summary": summary,
        "points": pick_points(paras, start, stop, limit=limit),
        "cases": pick_cases(paras, start, stop, limit=3),
    }


def extract_assignments(paras: list[str]) -> list[dict]:
    start = first_index(paras, "□ 과제목록 □")
    if start < 0:
        return []
    result: list[dict] = []
    current: dict | None = None
    for text in paras[start + 1 : start + 40]:
        if text.startswith("<과제"):
            if current:
                result.append(current)
            current = {"title": text, "materials": []}
        elif current and (text.startswith("<판례>") or text.startswith("<논문>") or text.startswith("대법원 ") or "김제완" in text):
            current["materials"].append(text)
    if current:
        result.append(current)
    return result[:6]


def collect_exam(paras: list[str], start: int, max_items: int = 8) -> list[str]:
    stops = [idx for idx, text in enumerate(paras[start + 1 :], start + 1) if text.startswith("<기출문제>")]
    stop = stops[0] if stops else min(start + 18, len(paras))
    items: list[str] = []
    for text in paras[start : min(stop, start + 18)]:
        if len(text) < 8:
            continue
        clipped = text if len(text) <= 900 else text[:900].rstrip() + "..."
        items.append(clipped)
        if len(items) >= max_items:
            break
    return items


def extract_exams(paras: list[str]) -> dict:
    hits = [idx for idx, text in enumerate(paras) if text.startswith("<기출문제>")]
    by_title = {paras[idx]: collect_exam(paras, idx) for idx in hits if idx > 300}
    return {
        "general": [
            {
                "title": "<기출문제> 1999. 2학기 중간고사 - 법인",
                "items": by_title.get("<기출문제> 1999. 2학기 중간고사", []),
            }
        ],
        "property": [
            {
                "title": "용익물권 사례형 점검문제",
                "items": [
                    "전세권설정등기가 임대차보증금 반환채권을 담보하기 위해 이루어진 경우, 보증금반환의무와 전세권설정등기 말소의무의 관계를 동시이행 항변으로 구성할 수 있는지 논하시오.",
                    "건물소유 목적 토지임대차에서 임차권, 지상권, 전세권의 기능 차이와 대항력 확보 방법을 비교하시오.",
                    "지역권의 부종성, 불가분성, 시효취득 가능성을 사례에 적용하여 설명하시오.",
                ],
            }
        ],
        "obligation": [
            {
                "title": "<기출문제> 2002. 중간고사문제 - 증여",
                "items": by_title.get("<기출문제> 2002. 중간고사문제", []),
            },
            {
                "title": "<기출문제> 채권총론 중간고사 문제 (2001. 2학기)",
                "items": by_title.get("<기출문제> 채권총론 중간고사 문제 (2001. 2학기)", []),
            },
            {
                "title": "<기출문제> 채권법론(상) 중간고사 문제 (2005. 1학기)",
                "items": by_title.get("<기출문제> 채권법론(상) 중간고사 문제 (2005. 1학기)", []),
            },
        ],
    }


def build_data(paras: list[str], hwpx: Path) -> dict:
    next_chapters = [
        "제 1 장 매매",
        "제 2 장 증여",
        "제 3 장 교환",
        "제2강계약각론",
        "제3강물건용익",
        "제4강계약각론",
        "제5강계약각론",
        "제6강계약각론",
        "제7강계약책임",
        "제8강계약책임",
        "제9강계약책임",
        "제10강계약책임",
        "제11강",
        "<기출문제>",
    ]
    notes = [
        make_note(
            paras,
            "sale-formation",
            "매매계약의 성립과 부수의무",
            "제1강 계약각론(1)",
            article_range(563, 568),
            "매매는 재산권 이전과 대금지급의 합의로 성립하며, 목적물과 대금 특정 가능성, 정보제공ㆍ고지의무가 핵심 쟁점이다.",
            "제 2 절 매매의 성립",
            ["제 3 절", "제 2 장 증여"],
        ),
        make_note(
            paras,
            "gift",
            "증여와 부담부증여",
            "제1강 계약각론(1)",
            article_range(554, 562),
            "서면 없는 증여의 해제, 부담부증여의 유상계약적 성격, 기이행 부분의 의미를 구별해 보아야 한다.",
            "제 2 장 증여",
            ["제 3 장 교환", "제2강계약각론"],
        ),
        make_note(
            paras,
            "exchange",
            "교환과 보충금",
            "제1강 계약각론(1)",
            article_range(596, 597),
            "교환은 금전 이외 재산권의 상호 이전 계약이고, 보충금 약정이 붙으면 매매대금 법리가 준용된다.",
            "제 3 장 교환",
            ["제2강계약각론", "제 1 절 서설"],
        ),
        make_note(
            paras,
            "lease",
            "임대차와 보증금",
            "제2강 계약각론(2)",
            article_range(618, 654),
            "임대차에서는 차임, 존속기간, 보증금의 담보적 기능, 임차권의 대항력과 종료 시 정산 구조가 중심이다.",
            "제2강계약각론",
            ["제3강물건용익", "제4강계약각론"],
            limit=8,
        ),
        make_note(
            paras,
            "superficies",
            "지상권",
            "제3강 물건용익",
            article_range(279, 290),
            "지상권은 타인의 토지를 건물ㆍ공작물ㆍ수목 소유 목적으로 사용하는 물권으로, 임대차와의 기능 비교가 중요하다.",
            "지상권",
            ["지역권", "전세권", "제4강계약각론"],
        ),
        make_note(
            paras,
            "easement",
            "지역권",
            "제3강 물건용익",
            article_range(291, 302),
            "지역권은 요역지와 승역지의 관계에서 이해해야 하며, 부종성ㆍ불가분성ㆍ시효취득 쟁점이 반복된다.",
            "지역권",
            ["전세권", "제4강계약각론"],
        ),
        make_note(
            paras,
            "chonsegwon",
            "전세권",
            "제3강 물건용익",
            article_range(303, 319),
            "전세권은 용익과 담보가 결합된 물권으로, 임대차보증금 반환채권 담보 목적의 설정등기 사례를 따로 보아야 한다.",
            "전세권",
            ["제4강계약각론", "사용대차"],
            limit=8,
        ),
        make_note(
            paras,
            "loan-use-money",
            "사용대차와 소비대차",
            "제4강 계약각론(3)",
            article_range(598, 617),
            "소비대차와 사용대차는 무상성ㆍ목적물 반환 방식ㆍ차주 보호의 구조가 다르므로 임대차와 함께 비교해야 한다.",
            "제4강계약각론",
            ["제5강계약각론", "제6강계약각론"],
        ),
        make_note(
            paras,
            "work-mandate-employment",
            "노무제공형 계약",
            "제5강 계약각론(4)",
            article_range(655, 674) + article_range(680, 702),
            "고용ㆍ도급ㆍ위임ㆍ임치는 노무제공의 결과 귀속, 재량, 보수, 해지 가능성에서 차이가 난다.",
            "제5강계약각론",
            ["제6강계약각론", "제7강계약책임"],
            limit=8,
        ),
        make_note(
            paras,
            "partnership-settlement",
            "조합ㆍ현상광고ㆍ종신정기금ㆍ화해",
            "제6강 계약각론(5)",
            article_range(675, 679) + article_range(703, 733),
            "조합은 단순한 쌍무계약 해제보다 탈퇴ㆍ해산ㆍ청산의 틀로 처리하는 점이 중요하다.",
            "제6강계약각론",
            ["제7강계약책임", "제8강계약책임"],
            limit=8,
        ),
        make_note(
            paras,
            "default-liability",
            "채무불이행책임의 일반요건",
            "제7강 계약책임(1)",
            article_range(387, 397),
            "계약이행상의 장애는 이행지체ㆍ이행불능ㆍ불완전이행과 손해배상 요건을 나누어 보아야 한다.",
            "제7강계약책임",
            ["제8강계약책임", "제9강계약책임"],
            limit=8,
        ),
        make_note(
            paras,
            "simultaneous-risk",
            "동시이행ㆍ위험부담ㆍ채권자지체",
            "제8강 계약책임(2)",
            article_range(400, 403) + article_range(536, 538),
            "쌍무계약에서는 동시이행 항변, 위험부담, 채권자지체가 이행거절과 반대급부 존속을 가르는 기준이 된다.",
            "제8강계약책임",
            ["제9강계약책임", "제10강계약책임"],
            limit=8,
        ),
        make_note(
            paras,
            "termination-damages",
            "손해배상과 계약해제",
            "제9강 계약책임(3)",
            article_range(390, 398) + article_range(543, 553),
            "계약해제는 손해배상과 병존할 수 있지만, 최고ㆍ상당기간ㆍ해제권 발생 요건을 엄격히 확인해야 한다.",
            "제9강계약책임",
            ["제10강계약책임", "제11강"],
            limit=8,
        ),
        make_note(
            paras,
            "warranty",
            "매매ㆍ도급의 담보책임",
            "제10강 계약책임(4)",
            article_range(569, 584) + article_range(667, 672),
            "담보책임은 등가성ㆍ유상성에서 출발하며, 채무불이행책임과의 관계 및 제척기간을 함께 보아야 한다.",
            "제 1 장 매매계약에 따른 담보책임",
            ["제11강", "<기출문제>"],
            limit=8,
        ),
        make_note(
            paras,
            "juridical-person",
            "법인의 의의ㆍ능력ㆍ책임",
            "제11강 법인론",
            article_range(31, 97),
            "법인은 자연인이 아니면서 권리능력을 인정받은 주체이며, 목적범위ㆍ대표기관ㆍ불법행위책임을 한 묶음으로 보아야 한다.",
            "제11강",
            ["<기출문제>"],
            limit=10,
        ),
    ]
    return {
        "brand": "하랑재",
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "lecture": {
            "title": "법학전문대학원 2026학년도 1학기 민법 II 강의안ㆍ강의자료",
            "professor": "김제완",
            "sourceFile": str(hwpx),
            "publicTextPolicy": "공개 화면에는 조문별 주해 요약과 시험문제 칸만 노출하고, 원문 추출본은 로컬 작업용으로만 보관한다.",
        },
        "faculty": {
            "sourceUrl": "https://faculty.korea.ac.kr/kufaculty/jkim/index.do",
            "name": "김제완",
            "title": "고려대학교 법학전문대학원 교수",
            "phone": "02-3290-1899",
            "email": "jkim@korea.ac.kr",
            "sections": ["프로필", "연구업적", "강의/교육", "하랑재-소개/학위논문", "하랑재-연구성과", "기고/행사/보도"],
            "education": [
                "1998. 2. 고려대학교 대학원 법학박사, 1994. 2. 법학석사",
                "1996. University of Oxford 교환 대학원생",
                "1988. 사법연수원 제17기 수료, 1985. 제27회 사법시험 합격",
                "1985. 서울대학교 법과대학 졸업",
            ],
            "career": [
                "2000. 3.부터 고려대학교 법학전문대학원 교수",
                "법무부 민법개정위원회, 법조윤리협의회, 사학분쟁조정위원회 등에서 활동",
                "고려대학교 법학연구원장, 법학과장, 자유전공학부 학부장 등 역임",
                "민법, 금융거래, 소비자ㆍ임대차, 블록체인ㆍ스마트계약 등 민사법 쟁점 연구",
            ],
            "researchTracks": [
                "민법 일반, 계약법, 채권자취소권, 채무불이행과 계약해제",
                "금융거래법, 은행법, 예금토큰, 무권한 전자금융거래",
                "주택임대차와 상가임대차, 소비자ㆍ집합건물ㆍ공동주택 법제",
                "블록체인, 스마트계약, 탈중앙화 거래와 민사법",
                "법조윤리, 사법신뢰, 공익인권 및 사회적 책임",
            ],
            "teachingTracks": [
                "민법 II, 계약성립론, 계약책임, 채권양도ㆍ채무인수이론",
                "담보물권법, 저당권론, 특수담보제도론, 비교담보제도론",
                "대차계약론, 위임ㆍ임치론, 도급론, 조합이론",
                "소유권론, 용익물권론, 코먼로재산권론, 비교사법제도론",
                "금융거래법 일반이론, 부동산금융과 법, 법과 윤리",
            ],
            "harangjaeOutputs": [
                "지도학생 박사ㆍ석사 학위논문을 민사법 쟁점별로 축적",
                "공동연구와 공동저술을 하랑재 연구성과로 정리",
                "임대차, 금융, 담보, 채권자취소, 디지털금융 등 실무형 주제 다수",
                "졸업생ㆍ재학생의 연구 흐름을 조문별 주해와 연결",
            ],
            "mediaTopics": [
                "인공지능 시대의 법제, 블록체인 기술의 민사관계",
                "사법신뢰, 전관ㆍ후관예우, 법조윤리",
                "유류분, 주택임대차, 손해배상 제도 개선",
                "국가배상, 노동ㆍ인권, 사회적 책임 관련 기고와 판결 비평",
            ],
            "honors": [
                "석탑강의상, 우수강의상, 안암강의상 수상 다수",
                "석탑연구상 2022, 2025, 2026",
                "20년 장기근속표창 및 법무부장관 표창",
            ],
            "harangjae": {
                "meaning": "하랑재는 함께 높이 날 수 있는 곳, 밝은 웃음이 있는 연구실이라는 뜻을 담은 김제완 교수 연구실의 고유 이름이다.",
                "scope": "지도학생 학위논문, 공동 연구성과, 언론 기고ㆍ행사ㆍ보도를 한데 묶어 민사법 학습의 살아 있는 맥락으로 연결한다.",
            },
        },
        "assignments": extract_assignments(paras),
        "notes": notes,
        "exams": extract_exams(paras),
    }


def write_private_copy(paras: list[str], hwpx: Path) -> None:
    PRIVATE_DIR.mkdir(parents=True, exist_ok=True)
    out = PRIVATE_DIR / "kim_jewan_civil2_extracted.txt"
    out.write_text(
        f"source: {hwpx}\nextracted_at: {datetime.now().isoformat()}\n\n" + "\n".join(paras),
        encoding="utf-8",
    )


def update_index() -> None:
    path = ROOT / "index.html"
    html = path.read_text(encoding="utf-8")
    changed = False

    css_marker = "</style>"
    css = """

/* ---------- 하랑재 민법주해 ---------- */
.harang-page .gist{font-size:15px}
.harang-hero{display:grid;grid-template-columns:minmax(0,1.35fr) minmax(260px,.65fr);gap:18px;align-items:stretch;margin:16px 0 22px}
.harang-card,.harang-note,.harang-exam,.harang-topic{border:1px solid #dbe4ef;border-radius:18px;background:#fff;padding:16px 18px;box-shadow:0 10px 26px rgba(15,23,42,.06)}
.harang-card strong,.harang-note strong{color:#312e81}
.harang-grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:12px;margin:12px 0 20px}
.harang-chiprow{display:flex;flex-wrap:wrap;gap:8px;margin-top:12px}
.harang-chip{border:1px solid #c7d2fe;background:#eef2ff;color:#312e81;border-radius:999px;padding:5px 10px;font-size:12px;font-weight:900}
.harang-list{display:grid;gap:8px;margin-top:8px}
.harang-list li{margin-left:18px;color:var(--txt2)}
.harang-note{margin:22px 0;background:linear-gradient(135deg,#fff,#f8fbff)}
.harang-note h2,.harang-exam h2{margin-top:0}
.harang-note details,.harang-exam details{border:1px solid #e0e7ff;border-radius:14px;background:#fff;margin:8px 0;overflow:hidden}
.harang-note summary,.harang-exam summary{cursor:pointer;padding:10px 12px;font-weight:900;color:#312e81}
.harang-note .note-body,.harang-exam .note-body{padding:0 14px 14px}
.harang-note .source,.harang-card .source{font-size:12px;color:#667085;margin-top:8px}
.harang-exam{margin:24px 0;background:#fbfdff}
.harang-exam ol{padding-left:20px}
.harang-exam li{margin:7px 0;line-height:1.75}
.harang-page .profile-link{display:inline-flex;margin-top:8px;font-weight:900}
.harang-topics{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px}
.harang-topic h3{margin-top:0}
.mitem .mtop[href="#하랑재"],.clarity-fix .mitem .mtop[href="#하랑재"]{background:#fff7ed;border-color:#fed7aa;color:#9a3412!important}
@media (max-width:900px){.harang-hero,.harang-grid,.harang-topics{grid-template-columns:1fr}}
"""
    if ".harang-page .gist" not in html:
        html = html.replace(css_marker, css + "\n" + css_marker, 1)
        changed = True

    top_anchor = '<div class="mitem"><a class="mtop" data-pyeon="학습도구" href="#학습게임">CBT 게임센터</a></div>'
    top_insert = '<div class="mitem"><a class="mtop" data-pyeon="하랑재" href="#하랑재">하랑재</a></div>'
    if top_insert not in html:
        html = html.replace(top_anchor, top_insert + top_anchor, 1)
        changed = True

    nav_anchor = '<details class="pyeon game-nav"><summary>CBT 게임센터</summary>'
    nav_insert = '<details class="pyeon harang-nav"><summary>하랑재</summary><div class="arts"><a class="art-link full" data-art="하랑재" href="#하랑재">김제완 민법주해</a></div></details>\n'
    if nav_insert.strip() not in html:
        html = html.replace(nav_anchor, nav_insert + nav_anchor, 1)
        changed = True

    section_anchor = '<section class="art game-page" data-art="학습게임" data-pyeon="학습도구" id="학습게임">'
    section = """<section class="art harang-page" data-art="하랑재" data-pyeon="하랑재" id="하랑재">
<div class="crumb">하랑재 › 김제완 민법주해</div>
<h1>하랑재</h1>
<p class="gist">김제완 교수님의 민법 II 강의안과 연구실 자료를 조문별 민법 주해로 이어 붙이는 실시간 민법 교과서 공간입니다.</p>
<div id="harangjaeProfile"><p class="cmt-empty">하랑재 자료를 불러오는 중입니다.</p></div>
<div class="pager"><a href="#민법뉴스">‹ 민법뉴스</a><a href="#학습게임">CBT 게임센터 ›</a></div>
</section>
"""
    if 'id="하랑재"' not in html:
        html = html.replace(section_anchor, section + section_anchor, 1)
        changed = True

    script_anchor = "  function showArt(k){"
    script = r"""
  var HARANG_DATA=null,HARANG_PROMISE=null;
  function loadHarang(){
    if(HARANG_DATA)return Promise.resolve(HARANG_DATA);
    if(HARANG_PROMISE)return HARANG_PROMISE;
    HARANG_PROMISE=fetch('assets/harangjae_civil2_notes.json?v=20260610')
      .then(function(r){if(!r.ok)throw new Error('하랑재 자료를 불러오지 못했습니다.');return r.json();})
      .then(function(data){HARANG_DATA=data;return data;});
    return HARANG_PROMISE;
  }
  function harangEsc(v){return String(v==null?'':v).replace(/[&<>"']/g,function(ch){return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[ch];});}
  function renderHarangjaePage(){
    var root=document.getElementById('harangjaeProfile');
    if(!root||root.dataset.ready)return;
    root.dataset.ready='1';
    loadHarang().then(function(data){
      var f=data.faculty||{},lecture=data.lecture||{};
      var sectionChips=(f.sections||[]).map(function(x){return '<span class="harang-chip">'+harangEsc(x)+'</span>';}).join('');
      var education=(f.education||[]).map(function(x){return '<li>'+harangEsc(x)+'</li>';}).join('');
      var career=(f.career||[]).map(function(x){return '<li>'+harangEsc(x)+'</li>';}).join('');
      var honors=(f.honors||[]).map(function(x){return '<li>'+harangEsc(x)+'</li>';}).join('');
      var assignments=(data.assignments||[]).map(function(a){
        return '<details><summary>'+harangEsc(a.title)+'</summary><div class="note-body"><ul>'+((a.materials||[]).map(function(m){return '<li>'+harangEsc(m)+'</li>';}).join(''))+'</ul></div></details>';
      }).join('');
      var topics=(data.notes||[]).map(function(n){
        return '<div class="harang-topic"><h3>'+harangEsc(n.title)+'</h3><p>'+harangEsc(n.summary)+'</p><p class="source">'+harangEsc(n.lecture)+' · '+(n.articles||[]).slice(0,5).map(harangEsc).join(', ')+(n.articles&&n.articles.length>5?' 외':'')+'</p></div>';
      }).join('');
      root.innerHTML='<div class="harang-hero"><div class="harang-card"><h2>김제완 교수 민법주해</h2><p>'+harangEsc(lecture.title||'민법 II 강의안')+'</p><p>'+harangEsc(f.harangjae&&f.harangjae.meaning||'하랑재')+'</p><div class="harang-chiprow">'+sectionChips+'</div><a class="profile-link" href="'+harangEsc(f.sourceUrl||'#')+'" target="_blank" rel="noopener noreferrer">고려대학교 교수소개 원문 보기</a></div><div class="harang-card"><h2>기본 정보</h2><p><strong>'+harangEsc(f.name)+'</strong> · '+harangEsc(f.title)+'</p><p>'+harangEsc(f.phone)+'<br>'+harangEsc(f.email)+'</p><p class="source">'+harangEsc(lecture.publicTextPolicy||'')+'</p></div></div>'
        +'<div class="harang-grid"><div class="harang-card"><h2>학력</h2><ul class="harang-list">'+education+'</ul></div><div class="harang-card"><h2>경력과 연구</h2><ul class="harang-list">'+career+'</ul></div><div class="harang-card"><h2>상훈</h2><ul class="harang-list">'+honors+'</ul></div></div>'
        +'<h2>강의안 기반 조문 주해</h2><div class="harang-topics">'+topics+'</div>'
        +'<h2>과제 목록</h2><div class="harang-note">'+assignments+'</div>';
    }).catch(function(){root.innerHTML='<p class="cmt-empty">하랑재 자료를 불러오지 못했습니다.</p>';root.dataset.ready='';});
  }
  function ensureHarangSlot(sec,cls){
    var slot=sec.querySelector('.'+cls);
    if(slot)return slot;
    slot=document.createElement('div');
    slot.className=cls;
    var pager=sec.querySelector('.pager');
    if(pager)sec.insertBefore(slot,pager);else sec.appendChild(slot);
    return slot;
  }
  function renderHarangjaeArticle(sec,k){
    if(!sec||!/^제/.test(k))return;
    loadHarang().then(function(data){
      var notes=(data.notes||[]).filter(function(n){return (n.articles||[]).indexOf(k)>-1;});
      if(notes.length){
        var slot=ensureHarangSlot(sec,'harang-note');
        if(!slot.dataset.ready){
          slot.dataset.ready='1';
          slot.innerHTML='<h2>하랑재 주해</h2>'+notes.map(function(n){
            var points=(n.points||[]).map(function(p){return '<li>'+harangEsc(p)+'</li>';}).join('');
            var cases=(n.cases||[]).map(function(p){return '<li>'+harangEsc(p)+'</li>';}).join('');
            return '<details open><summary>'+harangEsc(n.title)+' <span class="note">'+harangEsc(n.lecture)+'</span></summary><div class="note-body"><p>'+harangEsc(n.summary)+'</p>'+(points?'<h3>착안점</h3><ul>'+points+'</ul>':'')+(cases?'<h3>판례 흐름</h3><ul>'+cases+'</ul>':'')+'<p class="source">자료: 김제완 교수 민법 II 강의안 기반 요약</p></div></details>';
          }).join('');
        }
      }
      var map={'제184조':'general','제372조':'property','제766조':'obligation'};
      var key=map[k];
      if(key&&data.exams&&data.exams[key]){
        var exam=ensureHarangSlot(sec,'harang-exam');
        if(!exam.dataset.ready){
          exam.dataset.ready='1';
          exam.innerHTML='<h2>시험문제</h2>'+data.exams[key].map(function(group){
            return '<details open><summary>'+harangEsc(group.title)+'</summary><div class="note-body"><ol>'+((group.items||[]).map(function(item){return '<li>'+harangEsc(item)+'</li>';}).join(''))+'</ol></div></details>';
          }).join('');
        }
      }
    }).catch(function(){});
  }
"""
    if "function renderHarangjaePage()" not in html:
        html = html.replace(script_anchor, script + "\n" + script_anchor, 1)
        changed = True

    old = "    renderLawSubject(found,k);\n    found.querySelectorAll('.talkslot').forEach(talkForm);"
    new = "    renderLawSubject(found,k);\n    if(k==='하랑재')renderHarangjaePage();\n    renderHarangjaeArticle(found,k);\n    found.querySelectorAll('.talkslot').forEach(talkForm);"
    if "renderHarangjaeArticle(found,k);" not in html:
        html = html.replace(old, new, 1)
        changed = True

    if changed:
        path.write_text(html, encoding="utf-8")


def main() -> None:
    hwpx = find_hwpx()
    paras = extract_paragraphs(hwpx)
    write_private_copy(paras, hwpx)
    data = build_data(paras, hwpx)
    ASSETS.mkdir(exist_ok=True)
    (ASSETS / "harangjae_civil2_notes.json").write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    update_index()
    print(json.dumps({"paragraphs": len(paras), "notes": len(data["notes"]), "asset": "assets/harangjae_civil2_notes.json"}, ensure_ascii=False))


if __name__ == "__main__":
    main()
