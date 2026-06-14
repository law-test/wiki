import json
import re
from datetime import date
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "assets"
ARTICLES = ASSETS / "civil_procedure_articles.json"
COMMENTARIES = ASSETS / "civil_procedure_commentaries.json"
MANUAL_DIR = (
    Path("C:/cowork")
    / "법원직_민사소송법_OX"
    / "_실무제요"
)


def compact(text):
    return re.sub(r"\s+", " ", (text or "")).strip()


def split_sentences(text):
    text = compact(text)
    parts = re.split(r"(?<=[.다])\s+", text)
    return [p.strip() for p in parts if p.strip()]


def article_number_value(article_no):
    m = re.search(r"제(\d+)조(?:의(\d+))?", article_no or "")
    if not m:
        return 0, 0
    return int(m.group(1)), int(m.group(2) or 0)


def load_manual_index():
    snippets = []
    for path in sorted(MANUAL_DIR.glob("*.txt")):
        text = path.read_text(encoding="utf-8", errors="ignore")
        for line in text.splitlines():
            line = compact(line)
            if not line:
                continue
            if line.startswith(("제", "1.", "2.", "3.", "4.", "5.", "6.", "7.", "8.", "9.", "가.", "나.", "다.", "라.", "마.")):
                if 4 <= len(line) <= 70:
                    snippets.append(line)
    seen = set()
    result = []
    for line in snippets:
        key = re.sub(r"\s+", "", line)
        if key in seen:
            continue
        seen.add(key)
        result.append(line)
    return result


def find_manual_topics(row, manual_index):
    title = row.get("title") or ""
    chapter = row.get("chapter") or ""
    section = row.get("section") or ""
    candidates = []
    keywords = [title, chapter, section]
    keywords += re.split(r"[ㆍ·,()\s]+", title)
    keywords = [k for k in keywords if len(k) >= 2]
    for line in manual_index:
        score = 0
        for k in keywords:
            if k and k in line:
                score += min(len(k), 8)
        if score:
            candidates.append((score, line))
    candidates.sort(key=lambda x: (-x[0], len(x[1])))
    return [line for _, line in candidates[:3]]


def category(row):
    strong = " ".join(compact(row.get(k)) for k in ("part", "chapter", "section", "title"))
    body = compact(row.get("body"))
    text = strong + " " + body
    tests = [
        ("finality", ["판결의 확정", "집행정지", "판결확정", "확정증명"]),
        ("payment", ["독촉", "지급명령"]),
        ("public_notice", ["공시최고", "제권판결"]),
        ("retrial", ["재심", "준재심"]),
        ("appeal", ["항소", "상고", "항고", "재항고", "상소"]),
        ("evidence", ["증거", "증인", "감정", "검증", "문서", "서증", "증거보전", "당사자신문"]),
        ("service", ["송달", "공시송달", "우편송달"]),
        ("deadline", ["기일", "기간", "기일변경", "추후보완"]),
        ("cost", ["소송비용", "담보", "소송구조"]),
        ("jurisdiction", ["관할", "재판적", "소송목적의 값", "이송"]),
        ("party", ["당사자", "소송능력", "대표자", "보조참가", "공동소송", "선정당사자", "소송대리인"]),
        ("pleading", ["소장", "소의 제기", "청구", "답변서", "준비서면", "변론", "반소", "중간확인의 소"]),
        ("judgment", ["판결", "결정", "명령", "재판", "화해권고", "조서"]),
    ]
    for name, words in tests:
        haystack = strong if name == "party" else text
        if any(w in haystack for w in words):
            return name
    return "general"


CATEGORY_TEXT = {
    "jurisdiction": {
        "purpose": "담당 법원을 확정해 절차의 출발점을 안정시키는",
        "focus": "관할은 소 제기 단계에서 가장 먼저 확인할 사항이다. 전속관할인지 임의관할인지, 보통재판적인지 특별재판적인지에 따라 피고의 방어권과 절차경제가 달라진다.",
        "practice": "실무에서는 소장 접수 전에 관할 근거를 분명히 잡아 두어야 한다. 관할 위반은 이송, 각하, 항변권 행사 여부와 연결되므로 관할 원인 사실을 소장과 첨부자료에서 확인할 필요가 있다.",
    },
    "party": {
        "purpose": "절차의 주체와 절차행위 권한을 밝히는",
        "focus": "당사자 관련 규정은 소송요건과 절차행위의 효력을 좌우한다. 당사자능력, 소송능력, 대표권, 참가관계를 구별해야 절차상 흠을 줄일 수 있다.",
        "practice": "실무에서는 표시된 당사자와 실제 권리귀속 주체가 맞는지, 법정대리인이나 대표자의 권한이 소명되었는지, 공동소송이나 참가의 요건이 충족되는지 순서대로 점검한다.",
    },
    "cost": {
        "purpose": "절차 비용의 부담, 담보 제공, 구조 여부를 정리하는",
        "focus": "소송비용 규정은 재판 결과뿐 아니라 소송 수행 가능성에도 영향을 준다. 비용 부담의 원칙, 담보 제공 여부, 소송구조의 요건을 구별해서 보아야 한다.",
        "practice": "실무에서는 비용 부담 주체, 담보명령의 필요성, 구조결정의 범위가 사건 진행과 집행 단계에 미치는 효과를 함께 검토한다.",
    },
    "deadline": {
        "purpose": "기일과 기간으로 절차 진행의 시간표를 잡는",
        "focus": "기일ㆍ기간 규정은 신속한 진행과 방어권 보장의 균형을 잡는 장치이다. 기간의 기산점, 불변기간 여부, 추후보완 가능성을 구별해야 한다.",
        "practice": "실무에서는 송달일, 기간 만료일, 기일 통지 여부가 결정적이다. 기록상 일자와 송달증명을 확인하고, 기간 도과가 절차상 불이익으로 이어지는지 점검한다.",
    },
    "service": {
        "purpose": "소송서류가 당사자에게 적법하게 도달하는 방식을 밝히는",
        "focus": "송달은 절차 진행의 전제이다. 송달이 적법해야 답변기간, 상소기간, 확정 여부가 안정적으로 산정된다.",
        "practice": "실무에서는 송달받을 사람, 송달장소, 보충송달ㆍ유치송달ㆍ공시송달의 요건을 엄격히 확인한다. 송달 하자는 재판의 효력과 불복기간에 직접 영향을 준다.",
    },
    "pleading": {
        "purpose": "주장과 청구를 절차 안에 제출하고 정리하는 방식을 밝히는",
        "focus": "변론과 서면 관련 규정은 처분권주의와 변론주의가 실제로 작동하는 통로이다. 청구취지, 청구원인, 공격방어방법을 구별해 정리해야 한다.",
        "practice": "실무에서는 소장ㆍ답변서ㆍ준비서면의 기재가 쟁점 정리의 출발점이다. 누락된 주장은 석명, 보정, 실기한 공격방어방법 문제와 연결될 수 있다.",
    },
    "evidence": {
        "purpose": "주장된 사실을 어떤 자료와 방식으로 증명할지 밝히는",
        "focus": "증거규정은 주장책임과 증명책임을 재판에서 실현한다. 증거신청의 적법성, 필요성, 증거조사의 방식과 한계를 구별해야 한다.",
        "practice": "실무에서는 입증취지, 증거방법, 증거조사 가능성을 함께 본다. 문서ㆍ증인ㆍ감정ㆍ검증 등 각 증거방법별 요건과 불응 시 효과를 별도로 확인한다.",
    },
    "judgment": {
        "purpose": "법원의 절차상 또는 본안상 판단 형식을 정리하는",
        "focus": "재판 형식은 효력과 불복방법을 좌우한다. 판결ㆍ결정ㆍ명령, 본안판단ㆍ소송판단, 종국재판ㆍ중간재판을 구별해야 한다.",
        "practice": "실무에서는 주문, 이유, 송달, 확정 시점을 함께 확인한다. 재판의 흠은 경정, 보충, 불복, 재심 등 후속 절차와 연결된다.",
    },
    "appeal": {
        "purpose": "하급심 판단에 대한 상급심 심사 절차를 정리하는",
        "focus": "상소규정은 확정 전 불복의 통로이다. 상소기간, 상소이익, 불복 범위, 심판 범위를 구별해야 한다.",
        "practice": "실무에서는 판결 송달일과 상소장 제출일을 먼저 확인한다. 항소ㆍ상고ㆍ항고는 심급 구조와 심사대상이 다르므로 불복이유와 제출서류를 달리 정리한다.",
    },
    "retrial": {
        "purpose": "확정재판에 중대한 하자가 있을 때 예외적으로 다시 다투는 통로를 여는",
        "focus": "재심은 확정판결의 안정성과 실체적 정의가 충돌하는 영역이다. 재심사유, 제기기간, 대상 재판을 엄격히 보아야 한다.",
        "practice": "실무에서는 재심사유를 추상적으로 주장하는 것만으로 부족하고, 어느 확정재판에 어떤 사유가 언제 발생ㆍ인지되었는지를 구체적으로 정리해야 한다.",
    },
    "payment": {
        "purpose": "금전 등 일정한 청구의 간이ㆍ신속한 집행권원 확보 절차를 정리하는",
        "focus": "독촉절차는 통상소송보다 간이하지만, 채무자의 이의가 있으면 소송절차로 이어질 수 있다. 신청요건과 송달, 이의신청의 효과가 핵심이다.",
        "practice": "실무에서는 청구의 종류와 금액, 채무자 주소, 송달 가능성을 먼저 확인한다. 지급명령은 신속성이 장점이지만 이의가 예상되면 통상소송과 비교해야 한다.",
    },
    "public_notice": {
        "purpose": "권리 또는 증서의 존재를 공시하고 이해관계인의 신고를 촉구하는 절차를 정리하는",
        "focus": "공시최고절차는 불특정 이해관계인을 상대로 권리신고 기회를 부여하고, 요건이 충족되면 제권판결 등으로 법률관계를 정리한다.",
        "practice": "실무에서는 신청권자, 공시최고 사유, 신고기간, 실권경고가 명확해야 한다. 공고와 제권판결의 효력 범위를 구별해서 보아야 한다.",
    },
    "finality": {
        "purpose": "재판의 확정과 집행정지 등 후속 효과를 정리하는",
        "focus": "확정과 집행정지는 권리실현 단계와 직결된다. 확정 시점, 증명서 발급, 상소ㆍ재심과 집행정지의 관계를 구별해야 한다.",
        "practice": "실무에서는 어떤 재판이 언제 확정되었는지, 집행정지를 구할 법원과 담보 제공 여부가 무엇인지 기록으로 확인한다.",
    },
    "general": {
        "purpose": "민사소송절차의 진행 기준과 효과를 구체화하는",
        "focus": "해당 조문은 절차의 공정성, 신속성, 경제성 가운데 어느 요소를 조정하는지 보아야 한다. 조문이 요구하는 요건과 그 효과를 분리해서 읽는 것이 중요하다.",
        "practice": "실무에서는 조문이 정한 주체, 신청 또는 직권 여부, 기간ㆍ방식, 위반 효과를 차례로 확인한다. 같은 장의 앞뒤 조문과 함께 보아야 적용 범위가 분명해진다.",
    },
}


def make_gist(row, info):
    title = row.get("title") or row.get("article_no")
    return f"{title}에 관한 기준을 두어 {info['purpose']} 규정이다."


def make_commentary(row, manual_topics):
    info = CATEGORY_TEXT[category(row)]
    title = row.get("title") or row.get("article_no")
    article_no = row.get("article_no")
    part = row.get("part") or "민사소송법"
    chapter = row.get("chapter") or ""
    section = row.get("section") or ""
    context = " · ".join(x for x in [part, chapter, section] if x)
    body_sentences = split_sentences(row.get("body", ""))
    short_body = body_sentences[0] if body_sentences else ""
    if len(short_body) > 180:
        short_body = short_body[:177].rstrip() + "..."

    topic_sentence = ""
    if manual_topics:
        topic_sentence = " 실무제요의 체계로 보면 " + ", ".join(manual_topics[:2]) + " 쟁점과 함께 읽을 수 있다."

    return {
        "subject": row.get("subject", "민사소송법"),
        "law_name": row.get("law_name", "민사소송법"),
        "article_no": article_no,
        "title": title,
        "gist": make_gist(row, info),
        "source_note": "법원실무제요 민사소송 1~3권의 체계와 민사소송법 조문을 바탕으로 공개용으로 재서술한 요약입니다.",
        "manual_topics": manual_topics,
        "explanations": [
            {
                "title": "1. 조문의 기능",
                "paragraphs": [
                    f"{article_no}는 {context} 부분에서 {title}을 정하는 조문이다. {short_body}",
                    f"이 조문은 단독으로 읽기보다 같은 편ㆍ장ㆍ절의 앞뒤 규정과 연결하여 보아야 한다.{topic_sentence}",
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


def main():
    articles = json.loads(ARTICLES.read_text(encoding="utf-8"))["items"]
    existing = {}
    if COMMENTARIES.exists():
        old = json.loads(COMMENTARIES.read_text(encoding="utf-8"))
        existing = {item["article_no"]: item for item in old.get("items", [])}

    manual_index = load_manual_index()
    items = []
    for row in articles:
        article_no = row.get("article_no")
        if article_no in existing and article_no == "제1조":
            preserved = dict(existing[article_no])
            preserved.setdefault("title", row.get("title"))
            preserved.setdefault("source_note", "법원실무제요 민사소송 1~3권의 체계와 민사소송법 조문을 바탕으로 공개용으로 재서술한 요약입니다.")
            items.append(preserved)
            continue
        topics = find_manual_topics(row, manual_index)
        items.append(make_commentary(row, topics))

    items.sort(key=lambda item: article_number_value(item.get("article_no")))
    output = {
        "updatedAt": date.today().isoformat(),
        "source": "법원실무제요 민사소송 1~3권 체계 참고, 민사소송법 전 조문 공개용 해설 초안",
        "items": items,
    }
    COMMENTARIES.write_text(
        json.dumps(output, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"wrote {len(items)} commentaries to {COMMENTARIES}")


if __name__ == "__main__":
    main()
