import json
import re
from datetime import date
from pathlib import Path

import requests


ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "assets"
COMMENTARIES = ASSETS / "criminal_law_commentaries.json"

SUPABASE_URL = "https://vtqbyznczhgkpylczxpe.supabase.co"
SUPABASE_KEY = "sb_publishable_7B7sH9voJSz0QZDks744Vw_vVctHzSr"


def compact(text):
    return re.sub(r"\s+", " ", (text or "")).strip()


def article_number_value(article_no):
    m = re.search(r"제(\d+)조(?:의(\d+))?", article_no or "")
    if not m:
        return 0, 0
    return int(m.group(1)), int(m.group(2) or 0)


def split_sentences(text):
    text = compact(text)
    parts = re.split(r"(?<=[.다])\s+", text)
    return [p.strip() for p in parts if p.strip()]


def fetch_criminal_articles():
    url = f"{SUPABASE_URL}/rest/v1/law_subject_articles"
    headers = {"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"}
    params = {
        "select": "subject,law_name,article_no,title,body,part,chapter,section,sort_base,sort_sub",
        "subject": "eq.형법",
        "order": "sort_base.asc,sort_sub.asc",
        "limit": "2000",
    }
    res = requests.get(url, headers=headers, params=params, timeout=40)
    res.raise_for_status()
    rows = res.json()
    if not rows:
        raise RuntimeError("형법 조문을 불러오지 못했습니다.")
    return rows


SPECIAL_RULE_WORDS = [
    "미수범",
    "예비",
    "음모",
    "상습",
    "자격정지",
    "벌금의 병과",
    "몰수",
    "추징",
    "친고죄",
    "반의사불벌",
    "고소",
    "고발",
    "준용",
]


def category(row):
    part = compact(row.get("part"))
    chapter = compact(row.get("chapter"))
    section = compact(row.get("section"))
    title = compact(row.get("title"))
    text = " ".join([part, chapter, section, title, compact(row.get("body"))])

    if "제1편 총칙" in part:
        if "적용범위" in chapter:
            return "scope"
        if "죄의 성립" in section or any(w in title for w in ["고의", "과실", "착오", "정당방위", "긴급피난", "자구행위", "책임", "미수", "예비", "음모", "공범", "교사", "방조"]):
            if any(w in title for w in ["미수", "예비", "음모"]):
                return "inchoate"
            if any(w in title for w in ["공범", "교사", "방조", "공동정범"]):
                return "accomplice"
            return "crime_general"
        if "형" in chapter:
            if any(w in title for w in ["선고유예", "집행유예", "가석방", "시효", "소멸", "기간"]):
                return "execution"
            return "punishment"
        return "general_part"

    if any(w in title for w in SPECIAL_RULE_WORDS):
        return "special_rule"
    if any(w in chapter for w in ["살인", "상해", "폭행", "과실치사", "낙태", "유기", "학대"]):
        return "life_body"
    if any(w in chapter for w in ["체포", "감금", "협박", "약취", "유인", "강간", "추행"]):
        return "liberty_sexual"
    if any(w in chapter for w in ["명예", "신용", "업무", "비밀", "주거"]):
        return "personality_space"
    if any(w in chapter for w in ["절도", "강도", "사기", "공갈", "횡령", "배임", "장물", "손괴", "권리행사"]):
        return "property"
    if any(w in chapter for w in ["공무", "도주", "범인은닉", "위증", "증거인멸", "무고"]):
        return "state_function"
    if any(w in chapter for w in ["문서", "인장", "통화", "유가증권", "인지"]):
        return "public_credit"
    if any(w in chapter for w in ["방화", "일수", "교통방해", "음용수", "아편", "폭발물"]):
        return "public_safety"
    if any(w in chapter for w in ["내란", "외환", "국기", "국교", "공안"]):
        return "national_legal_order"
    if any(w in chapter for w in ["성풍속", "도박", "복표", "신앙"]):
        return "social_morals"
    return "specific_crime"


CATEGORY_TEXT = {
    "scope": {
        "purpose": "형법이 언제, 어디서, 누구에게 적용되는지를 정하는",
        "focus": "적용범위 조문은 죄형법정주의와 형벌법규의 시간적ㆍ장소적 효력을 정리하는 출발점이다. 행위시법 원칙, 신법 적용, 국내범ㆍ국외범ㆍ외국인에 대한 적용을 구별해야 한다.",
        "practice": "사건에서는 행위시, 결과발생지, 행위자의 국적, 피해자의 지위, 재판확정 여부가 먼저 문제 된다. 특히 법률 변경이 있는 경우에는 범죄 성립과 형의 경중을 나누어 검토한다.",
    },
    "crime_general": {
        "purpose": "범죄 성립의 일반요건과 위법성ㆍ책임 판단 기준을 정하는",
        "focus": "총칙의 죄 부분은 구성요건해당성, 위법성, 책임을 순서대로 검토하게 하는 뼈대이다. 고의ㆍ과실, 위법성조각사유, 책임조각ㆍ감경사유를 혼동하지 않아야 한다.",
        "practice": "실무에서는 먼저 구성요건에 해당하는 사실을 확정하고, 정당방위ㆍ긴급피난 등 위법성조각사유와 책임능력ㆍ기대가능성 문제를 별도로 판단한다.",
    },
    "inchoate": {
        "purpose": "범죄가 완성되기 전 단계의 처벌 범위를 정하는",
        "focus": "미수ㆍ예비ㆍ음모 조문은 실행의 착수 전후를 구별한다. 미수는 실행의 착수가 있었으나 결과가 발생하지 않은 경우이고, 예비ㆍ음모는 더 앞선 준비 단계이다.",
        "practice": "사건에서는 실행의 착수시기, 중지 여부, 결과발생 가능성, 해당 죄에서 미수ㆍ예비ㆍ음모 처벌규정이 있는지를 순서대로 확인한다.",
    },
    "accomplice": {
        "purpose": "여러 사람이 범죄에 관여한 경우의 책임 귀속을 정하는",
        "focus": "공범 규정은 정범과 공범, 공동정범ㆍ교사범ㆍ방조범을 구별한다. 행위지배, 범의의 공동, 교사 또는 방조행위와 정범 실행 사이의 관련성이 핵심이다.",
        "practice": "실무에서는 각 관여자의 행위, 인식, 역할 분담, 실행행위와의 인과적 기여를 개별적으로 본다. 단순한 현장 존재나 사후 관여만으로 공범이 되는 것은 아니다.",
    },
    "punishment": {
        "purpose": "형벌의 종류ㆍ경중ㆍ병과ㆍ감경 등 형의 체계를 정하는",
        "focus": "형벌규정은 법정형을 구체 사건의 처단형과 선고형으로 이어 주는 기준이다. 형의 종류, 경중, 가중ㆍ감경, 미결구금 산입 등을 구별해야 한다.",
        "practice": "실무에서는 먼저 각 죄의 법정형을 확인하고, 경합범ㆍ누범ㆍ작량감경ㆍ법률상 감경 사유를 거쳐 처단형 범위를 계산한다.",
    },
    "execution": {
        "purpose": "선고된 형의 집행, 유예, 시효, 소멸 효과를 정리하는",
        "focus": "집행 관련 조문은 형 선고 이후의 효과를 다룬다. 선고유예ㆍ집행유예ㆍ가석방ㆍ형의 시효ㆍ형의 실효는 요건과 효과가 서로 다르다.",
        "practice": "사건에서는 판결 확정일, 집행 개시 여부, 유예기간 중 사유 발생 여부, 시효기간 진행과 정지ㆍ중단 여부를 기록으로 확인한다.",
    },
    "general_part": {
        "purpose": "형법 총칙의 기본 기준을 보충하는",
        "focus": "총칙 조문은 각칙의 개별 범죄에 공통적으로 적용되는 기준이다. 조문이 범죄 성립, 형벌 산정, 형 집행 중 어느 단계에 작동하는지 먼저 구별한다.",
        "practice": "실무에서는 총칙 조문을 개별 구성요건에 기계적으로 붙이지 않고, 사건의 단계와 쟁점에 맞추어 적용한다.",
    },
    "special_rule": {
        "purpose": "개별 범죄군의 미수ㆍ상습ㆍ가중ㆍ준용 등 특칙을 정하는",
        "focus": "특칙 조문은 앞선 구성요건들의 처벌 범위나 효과를 확장하거나 제한한다. 어느 조문 또는 어느 장의 죄에 적용되는지를 정확히 잡아야 한다.",
        "practice": "실무에서는 본범 구성요건을 먼저 확정한 뒤, 미수범 처벌ㆍ상습가중ㆍ자격정지 병과ㆍ준용규정이 추가로 작동하는지 확인한다.",
    },
    "life_body": {
        "purpose": "사람의 생명ㆍ신체 안전을 침해하는 범죄의 구성요건과 법정형을 정하는",
        "focus": "생명ㆍ신체 범죄에서는 행위와 사망ㆍ상해 결과 사이의 인과관계, 고의 또는 과실, 결과적 가중 여부가 핵심이다.",
        "practice": "실무에서는 피해 결과의 정도, 행위 수단, 위험성, 예견가능성, 피해자의 상태를 통해 살인ㆍ상해ㆍ폭행ㆍ과실범 등을 구별한다.",
    },
    "liberty_sexual": {
        "purpose": "개인의 자유와 성적 자기결정권을 침해하는 범죄의 구성요건과 법정형을 정하는",
        "focus": "자유ㆍ성범죄에서는 폭행ㆍ협박ㆍ위계ㆍ위력, 동의의 유무와 유효성, 피해자의 연령ㆍ상태가 중요하다.",
        "practice": "실무에서는 행위 당시의 구체적 상황, 피해자 의사 억압 정도, 행위태양, 보호대상 요건을 세밀하게 확인한다.",
    },
    "personality_space": {
        "purpose": "명예ㆍ신용ㆍ업무ㆍ사생활ㆍ주거의 평온을 보호하는 범죄의 구성요건과 법정형을 정하는",
        "focus": "이 영역에서는 표현 또는 침입 행위의 의미, 공연성ㆍ전파가능성, 업무방해의 위계ㆍ위력, 주거의 평온 침해 여부가 쟁점이 된다.",
        "practice": "실무에서는 발언의 맥락, 상대방과 전달 범위, 업무의 현실적 방해 위험, 공간 이용관계와 승낙 범위를 함께 본다.",
    },
    "property": {
        "purpose": "재산권과 거래질서를 침해하는 범죄의 구성요건과 법정형을 정하는",
        "focus": "재산범죄에서는 객체의 타인성, 처분행위, 불법영득의사, 기망ㆍ협박ㆍ보관관계ㆍ임무위배를 구별해야 한다.",
        "practice": "실무에서는 재산상 이익의 이동, 피해자의 처분의사, 피고인의 보관자 지위 또는 타인의 사무처리 지위, 손해 발생을 구체적으로 본다.",
    },
    "state_function": {
        "purpose": "국가의 사법ㆍ공무 작용을 방해하는 범죄의 구성요건과 법정형을 정하는",
        "focus": "공무ㆍ사법기능 관련 범죄는 공무의 적법성, 직무집행의 현실성, 증거와 진술의 진실성, 국가기관 기능 침해 여부가 핵심이다.",
        "practice": "실무에서는 대상 공무나 재판절차가 무엇인지, 행위가 그 기능을 실제로 방해할 위험이 있는지, 고의와 목적이 인정되는지를 확인한다.",
    },
    "public_credit": {
        "purpose": "문서ㆍ통화ㆍ유가증권ㆍ인장 등 공공의 신용을 보호하는 범죄의 구성요건과 법정형을 정하는",
        "focus": "공공신용 범죄에서는 위조ㆍ변조ㆍ작성권한, 행사 목적, 문서성 또는 유가증권성, 진정성에 대한 사회적 신뢰가 중요하다.",
        "practice": "실무에서는 명의인, 작성권한, 내용의 진실성과 형식의 진정성을 나누어 본다. 실제 행사 여부와 행사 목적도 별도로 확인한다.",
    },
    "public_safety": {
        "purpose": "공공의 안전과 보건을 침해하는 위험범의 구성요건과 법정형을 정하는",
        "focus": "공공안전 범죄에서는 개인 피해보다 불특정 또는 다수인에 대한 위험 발생이 중요하다. 추상적 위험범인지 구체적 위험범인지도 구별해야 한다.",
        "practice": "실무에서는 행위 장소, 위험 확산 가능성, 공중의 이용관계, 위험 발생 정도를 중심으로 구성요건 해당성을 판단한다.",
    },
    "national_legal_order": {
        "purpose": "국가의 존립ㆍ대외관계ㆍ공공질서를 침해하는 범죄의 구성요건과 법정형을 정하는",
        "focus": "국가적 법익에 관한 범죄는 보호법익이 크고 법정형이 무겁다. 목적, 단체성, 외국 또는 적국과의 관계, 공공질서 침해 위험이 중요하다.",
        "practice": "실무에서는 행위자의 목적과 행위의 객관적 위험성, 실행 단계, 공범관계를 신중히 구별한다.",
    },
    "social_morals": {
        "purpose": "사회적 풍속ㆍ도박질서ㆍ종교적 평온 등 사회적 법익을 보호하는 범죄의 구성요건과 법정형을 정하는",
        "focus": "사회적 법익 범죄는 개인 피해보다 사회질서 침해 여부가 중심이다. 행위의 공개성, 영업성, 반복성, 사회적 위험성을 함께 보아야 한다.",
        "practice": "실무에서는 단순한 사적 행위와 형벌권이 개입할 정도의 사회적 위험을 구별하고, 상습성이나 영리성을 별도로 확인한다.",
    },
    "specific_crime": {
        "purpose": "형법 각칙상 개별 범죄의 구성요건과 법정형을 정하는",
        "focus": "각칙 조문은 보호법익, 행위주체, 행위객체, 행위태양, 결과와 법정형을 함께 읽어야 한다.",
        "practice": "실무에서는 먼저 구성요건요소를 빠짐없이 나누고, 총칙상 고의ㆍ착오ㆍ미수ㆍ공범ㆍ경합범 규정이 어떻게 붙는지 확인한다.",
    },
}


def special_gist(row, info):
    title = row.get("title") or row.get("article_no")
    if title == "미수범" or "미수범" in title:
        return "앞선 범죄군에 대하여 미수 단계도 처벌할지를 정하는 특칙이다."
    if "예비" in title or "음모" in title:
        return "범죄 실행에 이르기 전 준비ㆍ합의 단계의 처벌 범위를 정하는 특칙이다."
    if "상습" in title:
        return "반복적 범행 습벽이 인정되는 경우 형을 가중하는 특칙이다."
    if "준용" in title:
        return "같은 장 또는 관련 범죄군에 다른 조문의 효과를 끌어와 적용하는 연결 규정이다."
    return f"{title}에 관한 기준을 두어 {info['purpose']} 규정이다."


def make_commentary(row):
    info = CATEGORY_TEXT[category(row)]
    article_no = row.get("article_no")
    title = row.get("title") or article_no
    part = row.get("part") or "형법"
    chapter = row.get("chapter") or ""
    section = row.get("section") or ""
    context = " · ".join(x for x in [part, chapter, section] if x)
    sentences = split_sentences(row.get("body", ""))
    first = sentences[0] if sentences else ""
    if len(first) > 190:
        first = first[:187].rstrip() + "..."

    return {
        "subject": "형법",
        "law_name": row.get("law_name", "형법"),
        "article_no": article_no,
        "title": title,
        "gist": special_gist(row, info),
        "source_note": "형법 조문과 형법 체계를 바탕으로 공개용으로 재서술한 조문 해설 초안입니다.",
        "explanations": [
            {
                "title": "1. 조문의 기능",
                "paragraphs": [
                    f"{article_no}는 {context} 부분에서 {title}을 정하는 조문이다. {first}",
                    "형법 조문은 먼저 보호법익과 구성요건을 확인하고, 그 다음 총칙상 고의ㆍ위법성ㆍ책임ㆍ미수ㆍ공범ㆍ경합범 규정이 붙는지를 검토하는 방식으로 읽는다.",
                ],
            },
            {
                "title": "2. 형법상 읽는 방법",
                "paragraphs": [
                    info["focus"],
                    info["practice"],
                ],
            },
        ],
    }


def main():
    rows = fetch_criminal_articles()
    rows.sort(key=lambda row: article_number_value(row.get("article_no")))
    items = [make_commentary(row) for row in rows]
    output = {
        "updatedAt": date.today().isoformat(),
        "source": "형법 전 조문 공개용 해설 초안",
        "items": items,
    }
    COMMENTARIES.write_text(
        json.dumps(output, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"wrote {len(items)} commentaries to {COMMENTARIES}")


if __name__ == "__main__":
    main()
