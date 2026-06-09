from __future__ import annotations

import html
import json
import re
import zipfile
from pathlib import Path

from pypdf import PdfReader


ROOT = Path(__file__).resolve().parents[1]
PRIVATE_OUT = ROOT.parent / "law-test-private"
OUT_JSON = PRIVATE_OUT / "case_king_questions.json"
OUT_SQL = PRIVATE_OUT / "supabase_case_king_questions.sql"
OUT_HWPX = PRIVATE_OUT / "case_king_questions.hwpx"
STANDARD_PDFS = [
    (
        "민법",
        [
            ROOT / "tmp_standard_cases" / "civil.pdf",
            Path(r"D:/2026_04_09_시작/변호사업무_2024_10_21/법학경시대회/230425 민법 표준판례 2023년 (1) (3).pdf"),
        ],
    ),
    (
        "형법",
        [
            ROOT / "tmp_standard_cases" / "criminal.pdf",
            Path(r"D:/2026_04_09_시작/변호사업무_2024_10_21/법학경시대회/2023형법표준판례 선정연구보고서(116.수정) (2).pdf"),
        ],
    ),
    (
        "헌법",
        [
            ROOT / "tmp_standard_cases" / "constitutional.pdf",
            Path(r"D:/2026_04_09_시작/변호사업무_2024_10_21/법학경시대회/헌법 표준판례 (1).pdf"),
        ],
    ),
]


TERMS = """
관습법 법적 확신 법적 규범 법원 제정법 조리 사실인 관습 신의성실 권리남용 반사회질서
불공정한 법률행위 착오 사기 강박 의사표시 통정허위표시 비진의표시 무효 취소 추인
대리권 표현대리 무권대리 복대리 대리행위 현명주의 소멸시효 취득시효 제척기간 기산점
중단 정지 완성 자주점유 타주점유 선의 악의 과실 무과실 점유개정 간접점유 점유보조자
점유매개관계 선의취득 등기 점유 물권변동 물권적 청구권 소유권 공유 합유 총유 명의신탁
부동산실명법 유치권 질권 저당권 근저당권 전세권 지상권 지역권 담보물권 피담보채권
우선변제권 경매 배당이의 변제 공탁 상계 채무불이행 이행지체 이행불능 불완전이행
손해배상 과실상계 손익상계 위약금 계약금 해제 해지 원상회복 위험부담 채권자대위권
채권자취소권 사해행위 채권양도 채무인수 변제자대위 부당이득 불법행위 사용자책임
공작물책임 공동불법행위 명의대여자 책임 매매 임대차 사용대차 도급 위임 사무관리 조합
화해 증여 소비대차 임차권 대항력 보증금 권리금 전대차 동시이행 항변권 하자담보책임
담보책임 계약해제 사정변경 신뢰보호 금반언 위자료 재산분할 사실심 변론종결일 혼인 이혼
친권 양육권 부양 상속 상속포기 한정승인 상속회복청구권 유류분 특별수익 기여분 대습상속
유증 유언 유언집행자 사인증여 유언철회 부담부 유증 유류분반환청구권 반환의무 원물반환
가액반환 부진정연대채무 연대채무 불가분채무 보증채무 주채무 구상권 변제충당 이행보조자
안전배려의무 보호의무 설명의무 채권증서 반대급부 사실심 변론종결 확정판결 기판력 기속력
법률행위 해제권 형성권 항변권 청구권 준물권행위 처분행위 보존행위 관리행위 법률상 원인
선량한 풍속 사회질서 정당한 사유 특별한 사정 법률관계 등기명의인 선량한 관리자의 주의
상당인과관계 예견가능성 통상손해 특별손해 정신적 손해 청구권자 권리능력 행위능력 제한능력자
미성년자 피성년후견인 주소 부재자 실종선고 법인 정관 대표권 이사회 총회 법인격부인
법인 아닌 사단 종중 재단법인 사단법인 선의의 제3자 대항요건 통지 승낙 질권설정자 질권자
목적물반환청구권 반환청구권 소유의 의사 점유권 점유회수청구권 점유보호청구권 자력구제
혼동 첨부 부합 혼화 가공 과실수취권 악의점유자 선의점유자 필요비 유익비 부속물매수청구권
지료 분묘기지권 관습상 법정지상권 법정지상권 공유물분할 명의개서 신탁 신탁재산 매도청구권
취소권자 사해의사 수익자 전득자 피보전채권 채무초과 무자력 채권자평등 책임재산 보전처분
가압류 가처분 최고 이행청구 재판상 청구 재산권 친족권 상속권 인격권 개인정보 자기결정권
명예훼손 초상권 퍼블리시티권 채무자 채권자 제3채무자 제3자 직접점유자 간접점유자 양도담보
소유권유보 반환청구 소유물방해제거청구권 방해예방청구권 소유물반환청구권 불법원인급여
불법원인 원인급여 부양의무 부부재산제 일상가사대리권 일상가사채무 연대책임 재산분할청구권
이혼소송 친생자 추정 친생부인 인지 입양 파양 후견 상속재산분할 협의분할 상속분 법정상속분
특별연고자 상속재산관리인 재산목록 유언능력 자필증서 공정증서 비밀증서 구수증서 녹음증서
검인 유언집행 유증의 승인 유증의 포기 대여금 구상금 임대차보증금 전부명령 추심명령
채권압류 추심권능 전부권능 배당요구 배당표 배당절차 경락 매각허가 경매절차 경매개시결정
"""


def compact(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def make_terms() -> list[str]:
    high_quality = {
        "관습법",
        "법적 확신",
        "법적 규범",
        "법원",
        "제정법",
        "조리",
        "사실인 관습",
        "신의성실",
        "신의칙",
        "권리남용",
        "반사회질서",
        "불공정한 법률행위",
        "착오",
        "사기",
        "강박",
        "의사표시",
        "통정허위표시",
        "비진의표시",
        "무효",
        "취소",
        "추인",
        "대리권",
        "표현대리",
        "무권대리",
        "복대리",
        "현명주의",
        "소멸시효",
        "취득시효",
        "제척기간",
        "기산점",
        "중단",
        "정지",
        "완성",
        "자주점유",
        "타주점유",
        "선의",
        "악의",
        "과실",
        "무과실",
        "점유개정",
        "간접점유",
        "점유보조자",
        "선의취득",
        "등기",
        "점유",
        "소유권",
        "공유",
        "합유",
        "총유",
        "명의신탁",
        "유치권",
        "질권",
        "저당권",
        "근저당권",
        "전세권",
        "지상권",
        "지역권",
        "경매",
        "배당이의",
        "변제",
        "공탁",
        "상계",
        "손해배상",
        "과실상계",
        "손익상계",
        "위약금",
        "계약금",
        "해제",
        "해지",
        "원상회복",
        "위험부담",
        "사해행위",
        "채권양도",
        "채무인수",
        "부당이득",
        "불법행위",
        "사용자책임",
        "공작물책임",
        "매매",
        "임대차",
        "사용대차",
        "도급",
        "위임",
        "사무관리",
        "조합",
        "화해",
        "증여",
        "소비대차",
        "임차권",
        "대항력",
        "보증금",
        "권리금",
        "전대차",
        "담보책임",
        "계약해제",
        "사정변경",
        "신뢰보호",
        "금반언",
        "위자료",
        "재산분할",
        "혼인",
        "이혼",
        "친권",
        "양육권",
        "부양",
        "상속",
        "상속포기",
        "한정승인",
        "상속회복청구권",
        "유류분",
        "특별수익",
        "기여분",
        "대습상속",
        "유증",
        "유언",
        "유언집행자",
        "사인증여",
        "유언철회",
        "반환의무",
        "원물반환",
        "가액반환",
        "연대채무",
        "보증채무",
        "주채무",
        "구상권",
        "변제충당",
        "채권증서",
        "반대급부",
        "확정판결",
        "기판력",
        "기속력",
        "법률행위",
        "해제권",
        "형성권",
        "항변권",
        "청구권",
        "처분행위",
        "보존행위",
        "관리행위",
        "대항요건",
        "통지",
        "승낙",
        "혼동",
        "첨부",
        "부합",
        "혼화",
        "가공",
        "필요비",
        "유익비",
        "지료",
        "분묘기지권",
        "공유물분할",
        "명의개서",
        "신탁",
        "신탁재산",
        "매도청구권",
        "사해의사",
        "수익자",
        "전득자",
        "채무초과",
        "무자력",
        "책임재산",
        "가압류",
        "가처분",
        "최고",
        "이행청구",
        "승인",
        "압류",
        "죄형법정주의",
        "법률주의",
        "명확성의 원칙",
        "유추적용금지",
        "형벌불소급의 원칙",
        "책임주의",
        "인과관계",
        "미필적 고의",
        "고의",
        "과실범",
        "위법성조각사유",
        "정당방위",
        "긴급피난",
        "자구행위",
        "책임조각사유",
        "기대가능성",
        "예비",
        "음모",
        "미수",
        "실행의 착수",
        "중지미수",
        "불능미수",
        "공동정범",
        "공모공동정범",
        "교사범",
        "종범",
        "방조범",
        "간접정범",
        "신분범",
        "부작위범",
        "결과적 가중범",
        "죄수",
        "상상적 경합",
        "실체적 경합",
        "몰수",
        "추징",
        "횡령죄",
        "배임죄",
        "사기죄",
        "절도죄",
        "강도죄",
        "주거침입죄",
        "업무방해죄",
        "명예훼손죄",
        "공연성",
        "위법성",
        "구성요건",
        "불법영득의사",
        "관습헌법",
        "합헌적 법률해석",
        "헌법소원심판",
        "위헌법률심판",
        "헌법의 최고규범성",
        "민주적 기본질서",
        "방어적 민주주의",
        "정당해산",
        "과잉금지원칙",
        "비례원칙",
        "평등원칙",
        "명확성원칙",
        "포괄위임금지원칙",
        "신뢰보호원칙",
        "소급입법금지원칙",
        "적법절차원칙",
        "자기책임원리",
        "기본권 제한",
        "본질적 내용",
        "인간의 존엄과 가치",
        "행복추구권",
        "일반적 행동자유권",
        "인격권",
        "개인정보자기결정권",
        "양심의 자유",
        "종교의 자유",
        "표현의 자유",
        "언론의 자유",
        "집회의 자유",
        "결사의 자유",
        "학문의 자유",
        "직업의 자유",
        "재산권",
        "선거운동",
        "공무담임권",
        "재판청구권",
        "평등권",
        "사회적 기본권",
        "권한쟁의심판",
        "탄핵심판",
    }
    expanded = set(high_quality)
    expanded.update(term.replace(" ", "") for term in high_quality if " " in term)
    out = list(dict.fromkeys(t for t in expanded if len(t) >= 2))
    return sorted(out, key=lambda x: (-len(x), x))


def source_paragraphs() -> list[dict[str, str]]:
    grouped: list[list[dict[str, str]]] = []
    for subject, paths in STANDARD_PDFS:
        path = next((candidate for candidate in paths if candidate.exists()), None)
        if path is None:
            continue
        grouped.append(pdf_source_paragraphs(subject, path))
    rows: list[dict[str, str]] = []
    max_len = max((len(group) for group in grouped), default=0)
    for idx in range(max_len):
        for group in grouped:
            if idx < len(group):
                rows.append(group[idx])
    return rows


def pdf_text(path: Path) -> str:
    reader = PdfReader(str(path))
    pages = []
    for page in reader.pages:
        pages.append(page.extract_text() or "")
    return "\n".join(pages)


def clean_pdf_text(text: str) -> str:
    text = text.replace("\u3000", " ").replace("\xa0", " ")
    text = re.sub(r"ﾠ|ㅤ", " ", text)
    text = re.sub(r"(?m)^\s*-\s*[ivxlcdm]+\s*-\s*$", "\n", text, flags=re.I)
    text = re.sub(r"(?m)^변호사시험의 자격시험을 위한 .*?표준판례.*$", "\n", text)
    text = re.sub(r"(?m)^제\s*\d+\s*편.*$", "\n", text)
    text = re.sub(r"(?m)^\s*\d+\s*$", "\n", text)
    text = re.sub(r"[ \t]+", " ", text)
    return text


def pdf_source_paragraphs(subject: str, path: Path) -> list[dict[str, str]]:
    text = clean_pdf_text(pdf_text(path))
    parts = re.split(r"(?m)^\s*(\d{1,4})\.\s*$", text)
    rows: list[dict[str, str]] = []
    for idx in range(1, len(parts), 2):
        number = parts[idx]
        body = parts[idx + 1]
        source = case_source(subject, number, body)
        summary = case_summary(body)
        if not summary:
            continue
        paragraphs = paragraph_windows(summary)
        for paragraph in paragraphs:
            if len(paragraph) >= 70:
                rows.append({"text": paragraph, "source": source, "url": "", "subject": subject})
    return rows


def case_source(subject: str, number: str, body: str) -> str:
    head = compact(body[:700])
    title = re.split(r"\(", head, maxsplit=1)[0].strip()
    title = re.sub(r"<쟁점>.*$", "", title).strip()
    case = re.search(r"\(([^()]{8,120}(?:판결|결정|전원재판부)[^()]*)\)", head)
    case_text = compact(case.group(1)) if case else ""
    return compact(f"{subject} 표준판례 {number}. {title} {case_text}")


def case_summary(body: str) -> str:
    match = re.search(
        r"<(?:판결요지|결정요지|결정·판결요지)>\s*(.*?)(?=<(?:판례선정이유|선정이유|참고판례)>|$)",
        body,
        flags=re.S,
    )
    if not match:
        return ""
    text = match.group(1)
    text = re.sub(r"\[[0-9]+\]\s*", "", text)
    text = re.sub(r"(?m)^\s*[①-⑳]\s*", "", text)
    text = compact(text)
    text = re.sub(r"\s+([,.;:])", r"\1", text)
    return text.strip("\"“” ")


def paragraph_windows(text: str) -> list[str]:
    sentences = [compact(s) for s in re.findall(r"[^.。!?！？]+[.。!?！？]?", text) if compact(s)]
    if not sentences:
        return []
    if len(sentences) <= 5:
        return [compact(" ".join(sentences))]
    out = []
    for idx in range(0, len(sentences), 3):
        chunk = compact(" ".join(sentences[idx : idx + 5]))
        if len(chunk) >= 70:
            out.append(chunk)
        if len(out) >= 3:
            break
    return out


def five_sentence_window(text: str) -> str:
    sentences = [s.strip() for s in re.findall(r"[^.。!?！？]+[.。!?！？]?", text) if s.strip()]
    if len(sentences) <= 5:
        return text
    hit = next((idx for idx, sentence in enumerate(sentences) if "(A)" in sentence), 0)
    start = max(0, min(hit - 2, len(sentences) - 5))
    return " ".join(sentences[start : start + 5])


def good_occurrence(text: str, term: str, idx: int | None = None) -> bool:
    if idx is None:
        idx = text.find(term)
    if idx < 0:
        return False
    left = text[idx - 1] if idx > 0 else ""
    right = text[idx + len(term)] if idx + len(term) < len(text) else ""
    hangul = re.compile(r"[가-힣]")
    if hangul.match(left) or hangul.match(right):
        return False
    short_ok = {
        "무효",
        "취소",
        "추인",
        "착오",
        "사기",
        "강박",
        "점유",
        "등기",
        "변제",
        "공탁",
        "상계",
        "해제",
        "해지",
    }
    if len(term.replace(" ", "")) <= 2 and term not in short_ok:
        return False
    if re.search(r"(없이|있는|없는|되어|하여|따라|대한|대하여|으로|로서|부터|까지|얼마동안|최고 이념|귀 책사유)", term):
        return False
    generic = {
        "법적",
        "규범",
        "사유",
        "사정",
        "권리",
        "의무",
        "책임",
        "청구",
        "계약",
        "사실인",
        "특별한",
        "정당한",
        "위임",
        "승인",
        "최고",
        "선의",
        "악의",
        "과실",
        "상속",
        "유언",
        "유증",
    }
    return term not in generic


def blank_variants(text: str, term: str) -> list[str]:
    variants: list[str] = []
    start = 0
    while True:
        idx = text.find(term, start)
        if idx < 0:
            break
        if good_occurrence(text, term, idx):
            question = text[:idx] + "(A)" + text[idx + len(term) :]
            variants.append(five_sentence_window(question))
        start = idx + len(term)
        if len(variants) >= 1:
            break
    return variants


def build_questions() -> list[dict[str, str | int]]:
    terms = make_terms()
    rows: list[dict[str, str | int]] = []
    seen: set[tuple[str, str]] = set()
    answer_counts: dict[str, int] = {}
    for para in source_paragraphs():
        text = para["text"]
        candidates = [term for term in terms if term in text]
        candidates = list(dict.fromkeys(candidates))
        for answer in candidates:
            if not quality_answer(answer, para["source"], text):
                continue
            if answer_counts.get(answer, 0) >= 8:
                continue
            for question in blank_variants(text, answer):
                if "(A)" not in question or len(question) < 60:
                    continue
                key = (question, answer)
                if key in seen:
                    continue
                seen.add(key)
                rows.append(
                    {
                        "id": len(rows) + 1,
                        "caseNo": para["source"] or "대법원 판례",
                        "question": question,
                        "answer": answer,
                        "source": para["source"],
                        "url": para["url"],
                        "type": "판례검색",
                        "hint": "띄어쓰기와 줄바꿈은 채점에서 무시됩니다.",
                    }
                )
                answer_counts[answer] = answer_counts.get(answer, 0) + 1
    return rows


def quality_answer(answer: str, source: str, text: str) -> bool:
    compact_answer = answer.replace(" ", "")
    broad = {
        "법률행위",
        "의사표시",
        "위법성",
        "불법행위",
        "무과실",
        "손해배상",
        "처분행위",
        "청구권",
        "항변권",
        "구상권",
        "수익자",
        "인격권",
        "평등권",
        "재산권",
        "기본권제한",
        "본질적내용",
        "점유",
        "등기",
        "변제",
        "공탁",
        "상계",
        "압류",
        "통지",
        "승낙",
        "매매",
        "임대차",
        "위임",
        "조합",
        "화해",
        "증여",
        "혼인",
        "이혼",
        "친권",
        "양육권",
        "부양",
        "소유권",
        "상속",
    }
    if compact_answer in broad:
        return False
    if len(compact_answer) < 3:
        return False
    if re.search(r"(행위단속법|법률 제|대법원|헌법재판소|피고인|피해자|원고|피고|갑|을|병)", answer):
        return False
    source_compact = source.replace(" ", "")
    text_head = text[:350].replace(" ", "")
    core_short = {
        "무효",
        "취소",
        "착오",
        "사기",
        "강박",
        "해제",
        "해지",
        "추인",
    }
    if len(compact_answer) <= 3 and compact_answer not in core_short:
        return compact_answer in source_compact
    return compact_answer in source_compact


def terms_from_text(text: str) -> list[str]:
    suffixes = (
        "청구권",
        "항변권",
        "취소권",
        "해제권",
        "책임",
        "의무",
        "요건",
        "효과",
        "행위",
        "계약",
        "등기",
        "점유",
        "시효",
        "원칙",
        "제도",
        "처분",
        "관계",
        "원인",
        "사유",
        "사정",
        "재산",
        "채권",
        "채무",
        "권리",
        "상속",
        "유언",
        "유증",
        "손해",
        "배상",
        "반환",
        "분할",
        "기준",
        "기간",
        "소송",
        "판결",
        "결정",
    )
    out: list[str] = []
    for quoted in re.findall(r"[\"'“‘]([가-힣][가-힣\s·ㆍ]{1,22})[\"'”’]", text):
        out.append(compact(quoted))
    for suffix in suffixes:
        pattern = rf"([가-힣]{{2,18}}(?:\s+[가-힣]{{1,10}}){{0,2}}{suffix})"
        out.extend(compact(match) for match in re.findall(pattern, text))
    cleaned: list[str] = []
    stop = {"경우", "사람", "당사자", "법원", "민법", "대법원", "판례", "특별한 사정", "정당한 사유"}
    for term in out:
        term = term.strip(" 은는이가을를의로서와과및,.;:()[]")
        if len(term.replace(" ", "")) < 3 or len(term) > 24:
            continue
        if re.search(r"(항에|조에|따른|사건에서|판결|결정|선고|관련된)", term):
            continue
        if re.search(r"(따라|대한|대하여|경우에는|경우|사유로|이유로|상태에서)", term):
            continue
        if re.match(r"^[0-9제]", term):
            continue
        if term in stop:
            continue
        cleaned.append(term)
    return sorted(list(dict.fromkeys(cleaned)), key=lambda x: (-len(x), x))


def write_json(rows: list[dict[str, str | int]]) -> None:
    PRIVATE_OUT.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")


def sql_quote(value: object) -> str:
    return "'" + str(value).replace("'", "''") + "'"


def write_sql(rows: list[dict[str, str | int]]) -> None:
    values = []
    for row in rows:
        values.append(
            "("
            + ",".join(
                [
                    str(row["id"]),
                    sql_quote(row["caseNo"]),
                    sql_quote(row["question"]),
                    sql_quote(row["answer"]),
                    sql_quote(row["source"]),
                    sql_quote(row["url"]),
                    sql_quote(row["type"]),
                ]
            )
            + ")"
        )
    sql = """create table if not exists public.case_king_questions (
  id integer primary key,
  case_no text not null,
  question text not null,
  answer text not null,
  source text,
  url text,
  type text default '판례검색',
  created_at timestamptz default now()
);

alter table public.case_king_questions enable row level security;

drop policy if exists "case king questions readable" on public.case_king_questions;

grant usage on schema public to anon, authenticated;

delete from public.case_king_questions;

insert into public.case_king_questions
  (id, case_no, question, answer, source, url, type)
values
"""
    sql += ",\n".join(values)
    sql += """
on conflict (id) do update set
  case_no = excluded.case_no,
  question = excluded.question,
  answer = excluded.answer,
  source = excluded.source,
  url = excluded.url,
  type = excluded.type;

drop function if exists public.get_case_king_question();
create or replace function public.get_case_king_question()
returns table (
  id integer,
  case_no text,
  question text,
  answer text,
  source text,
  url text,
  type text
)
language sql
security definer
set search_path = public
as $$
  select id, case_no, question, answer, source, url, type
  from public.case_king_questions
  order by random()
  limit 1;
$$;

revoke all on function public.get_case_king_question() from public;
grant execute on function public.get_case_king_question() to anon, authenticated;
"""
    OUT_SQL.write_text(sql, encoding="utf-8")


def write_hwpx(rows: list[dict[str, str | int]]) -> None:
    lines = [f"도전! 판례왕 표준판례 엄선 문제은행 {len(rows)}문제", "유형: 판례검색", ""]
    for row in rows:
        lines.append(f"{row['id']:04d}. {row['caseNo']}")
        lines.append(str(row["question"]))
        lines.append(f"정답: {row['answer']}")
        lines.append("")
    preview = "\n".join(lines)
    body = "\n".join(
        f'<hp:p><hp:run><hp:t>{html.escape(line)}</hp:t></hp:run></hp:p>' for line in lines
    )
    section = f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<hp:sec xmlns:hp="http://www.hancom.co.kr/hwpml/2011/paragraph">
{body}
</hp:sec>
"""
    with zipfile.ZipFile(OUT_HWPX, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("mimetype", "application/hwp+zip")
        zf.writestr("version.xml", '<?xml version="1.0" encoding="UTF-8"?><version app="HWP" ver="1.0"/>')
        zf.writestr("Preview/PrvText.txt", preview)
        zf.writestr("Contents/section0.xml", section)
        zf.writestr(
            "META-INF/manifest.xml",
            """<?xml version="1.0" encoding="UTF-8"?>
<manifest xmlns="urn:oasis:names:tc:opendocument:xmlns:manifest:1.0">
  <file-entry full-path="/" media-type="application/hwp+zip"/>
  <file-entry full-path="Contents/section0.xml" media-type="text/xml"/>
  <file-entry full-path="Preview/PrvText.txt" media-type="text/plain"/>
</manifest>
""",
        )


def main() -> None:
    rows = build_questions()
    if len(rows) < 100:
        raise SystemExit(f"too few quality questions, got {len(rows)}")
    write_json(rows)
    write_sql(rows)
    write_hwpx(rows)
    print(f"wrote {len(rows)} questions")


if __name__ == "__main__":
    main()
