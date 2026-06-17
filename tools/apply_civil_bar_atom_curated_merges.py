from __future__ import annotations

import json
import re
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "assets"
REPORTS = ROOT / "reports"
INPUT = ASSETS / "ox_msa_bar_exam_integrated_draft_v001.json"
OUT_JSON = ASSETS / "ox_msa_bar_exam_integrated_curated_v001.json"
OUT_AUDIT_JSON = REPORTS / "civil_bar_atom_curated_merge_audit.json"
OUT_AUDIT_MD = REPORTS / "civil_bar_atom_curated_merge_audit.md"


CURATED_MERGES = [
    {
        "ids": ["civil-bar-integrated-0580", "civil-bar-integrated-0585", "civil-bar-integrated-0586"],
        "rep": "공동저당 목적물에 채무자 소유 부동산과 물상보증인 소유 부동산이 함께 있으면, 채무자 소유 부동산이 그 가액 한도에서 피담보채권 전액을 먼저 부담한다.",
        "art": "제482조",
        "topic": "저당권",
        "reason": "공동저당에서 채무자 소유 부동산 우선 부담 법리",
    },
    {
        "ids": ["civil-bar-integrated-2664", "civil-bar-integrated-2665"],
        "rep": "근저당권이 말소된 뒤에는 피담보채무 부존재확인을 구할 이익이 없다.",
        "reason": "근저당권 말소 후 확인의 이익 부정",
    },
    {
        "ids": ["civil-bar-integrated-2637", "civil-bar-integrated-2640"],
        "rep": "공동소송적 보조참가에서 피참가인이 재심의 소를 취하하려면 참가인의 동의가 필요하다.",
        "reason": "공동소송적 보조참가인의 동의 필요",
    },
    {
        "ids": ["civil-bar-integrated-2603", "civil-bar-integrated-2685"],
        "rep": "답변서 진술간주만으로는 변론관할이 생기지 않는다.",
        "reason": "진술간주와 변론관할",
    },
    {
        "ids": ["civil-bar-integrated-0459", "civil-bar-integrated-2127"],
        "rep": "횡령금으로 채무 변제가 이루어진 경우 채권자가 악의라면 부당이득반환의무를 진다.",
        "reason": "횡령금 변제와 악의 채권자의 부당이득",
    },
    {
        "ids": ["civil-bar-integrated-4074", "civil-bar-integrated-4075"],
        "rep": "어음이 채권 지급과 관련하여 교부된 경우 특별한 사정이 없으면 지급을 위하여 교부된 것으로 추정한다.",
        "reason": "어음 교부의 지급을 위한 추정",
    },
    {
        "ids": ["civil-bar-integrated-0256", "civil-bar-integrated-0257"],
        "rep": "보증채무 자체의 이행지체로 생기는 지연손해금은 보증한도액과 별도로 부담한다.",
        "reason": "보증채무 이행지체 지연손해금",
    },
    {
        "ids": ["civil-bar-integrated-0318", "civil-bar-integrated-0440"],
        "rep": "지연손해금 약정은 손해배상액의 예정으로 추정되어, 과다하면 법원이 감액할 수 있다.",
        "reason": "지연손해금 약정과 손해배상액 예정",
    },
    {
        "ids": ["civil-bar-integrated-3825", "civil-bar-integrated-4458"],
        "rep": "무액면주식을 발행하면 자본금은 주식 발행가액의 2분의 1 이상으로서 권한 있는 기관이 자본금으로 계상하기로 한 금액의 총액이다.",
        "reason": "무액면주식 발행 시 자본금 산정",
    },
    {
        "ids": ["civil-bar-integrated-0373", "civil-bar-integrated-1188"],
        "rep": "매매예약완결권의 제척기간을 연장하기 위한 새로운 매매예약도 사해행위가 될 수 있다.",
        "reason": "예약완결권 제척기간 연장과 사해행위",
    },
    {
        "ids": ["civil-bar-integrated-3784", "civil-bar-integrated-3785"],
        "rep": "만기가 백지인 어음의 보충권은 어음 자체의 시효기간인 3년의 소멸시효에 걸린다.",
        "reason": "만기 백지어음 보충권 시효",
    },
    {
        "ids": ["civil-bar-integrated-4096", "civil-bar-integrated-4097"],
        "rep": "어음채권에 대한 압류는 원인채권의 소멸시효도 중단시킨다.",
        "reason": "어음채권 압류와 원인채권 시효중단",
    },
    {
        "ids": ["civil-bar-integrated-0313", "civil-bar-integrated-1532"],
        "rep": "주택임대차보호법상 임차권등기명령에 의한 임차권등기에는 소멸시효 중단 효력이 없다.",
        "reason": "임차권등기명령과 소멸시효 중단",
    },
    {
        "ids": ["civil-bar-integrated-0454", "civil-bar-integrated-2101"],
        "rep": "계약 해제로 인한 원상회복청구권에는 과실상계 법리가 적용되지 않는다.",
        "reason": "해제 원상회복과 과실상계",
    },
    {
        "ids": ["civil-bar-integrated-0055", "civil-bar-integrated-0056"],
        "rep": "3자간 등기명의신탁에서 신탁자가 부동산을 점유하고 있으면 매도인에 대한 소유권이전등기청구권의 소멸시효는 진행하지 않는다.",
        "reason": "3자간 등기명의신탁과 등기청구권 시효",
    },
    {
        "ids": ["civil-bar-integrated-3603", "civil-bar-integrated-4573"],
        "rep": "대표소송에서 책임발생 원인사실이 같고 법적 평가만 다르면 청구를 추가할 수 있다.",
        "reason": "대표소송의 청구 추가",
    },
    {
        "ids": ["civil-bar-integrated-0320", "civil-bar-integrated-0406"],
        "rep": "채권양도 통지를 받은 채무자는 그 통지가 도달한 다음 날부터 이행지체 책임을 진다.",
        "reason": "채권양도 통지 도달과 이행지체",
    },
    {
        "ids": ["civil-bar-integrated-0767", "civil-bar-integrated-0911"],
        "rep": "부동산 매매계약의 소유권이전등기청구권을 양도하려면 채무자인 매도인의 동의나 승낙이 필요하다.",
        "reason": "소유권이전등기청구권 양도와 매도인 동의",
    },
    {
        "ids": ["civil-bar-integrated-1802", "civil-bar-integrated-1972"],
        "rep": "제3자의 처분금지가처분등기만으로는 매도인의 소유권이전등기의무가 곧바로 이행불능이 되지 않는다.",
        "reason": "처분금지가처분등기와 이행불능",
    },
    {
        "ids": ["civil-bar-integrated-3304", "civil-bar-integrated-3306"],
        "rep": "합유 부동산에 관한 명의신탁 해지를 원인으로 한 소유권이전등기청구는 고유필수적 공동소송이다.",
        "reason": "합유 부동산 명의신탁 해지와 고유필수적 공동소송",
    },
    {
        "ids": ["civil-bar-integrated-2564", "civil-bar-integrated-2599"],
        "rep": "어떤 소멸시효기간이 적용되는지는 법률의 해석·적용 문제이므로 법원이 직권으로 판단할 수 있다.",
        "reason": "소멸시효기간 적용과 법원의 직권 판단",
    },
    {
        "ids": ["civil-bar-integrated-4845", "civil-bar-integrated-4846"],
        "rep": "위탁매매에서 매수인이 매매대금채무를 이행하지 않더라도 위탁매매인에게 귀책사유가 없으면 특별한 약정이나 관습이 없는 한 위탁매매인은 위탁자에게 그 대금채무를 이행할 책임이 없다.",
        "reason": "위탁매매와 매수인 대금채무 불이행",
    },
    {
        "ids": ["civil-bar-integrated-2608", "civil-bar-integrated-2609"],
        "rep": "가등기에 기한 본등기 이행을 명한 판결의 기판력은 그 가등기 자체의 말소청구에는 미치지 않는다.",
        "reason": "가등기 본등기 판결과 가등기 말소청구 기판력",
    },
]

DEFERRED_CANDIDATES = [
    {
        "ids": ["civil-bar-integrated-4399", "civil-bar-integrated-4400"],
        "reason": "감사 선임 생략과 감사위원회 생략은 범위가 달라 별도 검토 필요",
    },
    {
        "ids": ["civil-bar-integrated-2858", "civil-bar-integrated-2859"],
        "reason": "상계항변 항소이익 문장은 원문 표현에 '옳지 않음'이 섞여 있어 정답 구조 재검토 필요",
    },
]


def clean_text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def source_sort_key(label: str) -> tuple[int, int, str]:
    match = re.search(r"\ubcc0\uc2dc(\d+)\s+(\d+)\ubc88\s+(.+)", str(label or ""))
    if not match:
        return (0, 0, str(label or ""))
    return (-int(match.group(1)), int(match.group(2)), match.group(3))


def unique_sources(values: list[Any]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = clean_text(value)
        if text and text not in seen:
            seen.add(text)
            out.append(text)
    return sorted(out, key=source_sort_key)


def years_from_sources(src: list[str]) -> list[str]:
    seen: set[str] = set()
    years: list[str] = []
    for label in src:
        match = re.search(r"\ubcc0\uc2dc(\d+)", label)
        if not match:
            continue
        year = f"변시{int(match.group(1))}"
        if year not in seen:
            seen.add(year)
            years.append(year)
    return sorted(years, key=lambda value: -int(value.replace("변시", "")))


def grade_for(freq: int) -> str:
    if freq >= 7:
        return "S"
    if freq >= 5:
        return "A+"
    if freq >= 3:
        return "A"
    if freq == 2:
        return "B+"
    return "A"


def weight_for(freq: int) -> float:
    return round(min(1.0, 0.55 + 0.08 * max(1, freq)), 4)


def merge_group(spec: dict[str, Any], by_pid: dict[str, dict[str, Any]]) -> dict[str, Any]:
    members = [by_pid[pid] for pid in spec["ids"]]
    head = members[0].copy()
    src = unique_sources([source for item in members for source in (item.get("src") or [])])
    refs = unique_sources([source for item in members for source in (item.get("refs") or item.get("src") or [])])
    source_statements = [
        clean_text(statement)
        for item in members
        for statement in (item.get("sourceStatements") or [])
        if clean_text(statement)
    ]
    ids = [pid for item in members for pid in (item.get("ids") or [item.get("pid")]) if pid]
    head.update(
        {
            "pid": spec["ids"][0],
            "topic": spec.get("topic") or head.get("topic") or "",
            "rep": spec["rep"],
            "why": spec["rep"],
            "art": spec.get("art") or head.get("art") or "",
            "src": src,
            "refs": refs,
            "years": years_from_sources(src),
            "sourceText": " · ".join(src),
            "freq": len(src),
            "hot": len(src) >= 3,
            "ids": unique_sources(ids),
            "sourceStatements": source_statements[:12],
            "sourceAnswers": sorted({answer for item in members for answer in (item.get("sourceAnswers") or [item.get("a")]) if answer}),
            "grade": grade_for(len(src)),
            "weight": weight_for(len(src)),
            "curatedMerge": {
                "mergedFrom": spec["ids"],
                "reason": spec["reason"],
                "curatedAt": datetime.now(timezone.utc).isoformat(),
            },
        }
    )
    return head


def build() -> tuple[dict[str, Any], dict[str, Any]]:
    data = json.loads(INPUT.read_text(encoding="utf-8"))
    items = list(data.get("items") or [])
    by_pid = {item["pid"]: item for item in items}
    missing = [pid for spec in CURATED_MERGES for pid in spec["ids"] if pid not in by_pid]
    if missing:
        raise KeyError(f"Missing merge ids: {missing}")

    merged_ids = {pid for spec in CURATED_MERGES for pid in spec["ids"]}
    output_items: list[dict[str, Any]] = []
    for item in items:
        if item["pid"] in merged_ids:
            continue
        output_items.append(item)
    for spec in CURATED_MERGES:
        output_items.append(merge_group(spec, by_pid))
    output_items.sort(key=lambda item: (item.get("subject") or "", item.get("art") or "", item.get("pid") or ""))

    subject_counts = Counter(item.get("subject") or "" for item in output_items)
    freq_counts = Counter(int(item.get("freq") or 1) for item in output_items)
    answer_counts = Counter(item.get("a") or "" for item in output_items)
    payload = {
        "title": "변호사시험 민사법 선택형 1~15회 최소 원리 atom 통합 큐레이션본",
        "version": "civil-bar-integrated-curated-v001",
        "builtAt": datetime.now(timezone.utc).isoformat(),
        "source": f"assets/{INPUT.name}",
        "count": len(output_items),
        "inputCount": len(items),
        "curatedMergeGroupCount": len(CURATED_MERGES),
        "curatedMergedSourceCount": len(merged_ids),
        "deferredCandidateCount": len(DEFERRED_CANDIDATES),
        "subjects": dict(subject_counts),
        "answerCounts": dict(answer_counts),
        "freqCounts": dict(sorted(freq_counts.items())),
        "items": output_items,
    }
    audit = {
        "inputCount": len(items),
        "outputCount": len(output_items),
        "reduction": len(items) - len(output_items),
        "curatedMergeGroupCount": len(CURATED_MERGES),
        "curatedMergedSourceCount": len(merged_ids),
        "subjectCounts": dict(subject_counts),
        "answerCounts": dict(answer_counts),
        "freqCounts": dict(sorted(freq_counts.items())),
        "mergedGroups": [
            {
                "ids": spec["ids"],
                "rep": spec["rep"],
                "reason": spec["reason"],
                "src": merge_group(spec, by_pid)["src"],
            }
            for spec in CURATED_MERGES
        ],
        "deferredCandidates": DEFERRED_CANDIDATES,
    }
    return payload, audit


def render_md(audit: dict[str, Any]) -> str:
    lines = [
        "# 변호사시험 민사법 atom 큐레이션 병합",
        "",
        f"- 입력 atom: {audit['inputCount']:,}개",
        f"- 출력 atom: {audit['outputCount']:,}개",
        f"- 감소: {audit['reduction']:,}개",
        f"- 병합 그룹: {audit['curatedMergeGroupCount']:,}개",
        f"- 병합된 원 atom: {audit['curatedMergedSourceCount']:,}개",
        f"- 보류 후보: {len(audit['deferredCandidates']):,}개",
        f"- 출력 파일: `assets/{OUT_JSON.name}`",
        "",
        "## 과목별",
        "",
    ]
    for subject, count in sorted(audit["subjectCounts"].items()):
        lines.append(f"- {subject}: {count:,}개")
    lines.extend(["", "## 출제 빈도별", ""])
    for freq, count in sorted(audit["freqCounts"].items(), key=lambda row: int(row[0])):
        lines.append(f"- {freq}회 출처: {count:,}개")
    lines.extend(["", "## 병합한 그룹", ""])
    for index, group in enumerate(audit["mergedGroups"], start=1):
        lines.append(f"### {index}. {' · '.join(group['src'])}")
        lines.append(f"- 이유: {group['reason']}")
        lines.append(f"- 통합 문장: {group['rep']}")
        lines.append(f"- 원 pid: {', '.join(group['ids'])}")
        lines.append("")
    lines.extend(["## 보류한 후보", ""])
    for item in audit["deferredCandidates"]:
        lines.append(f"- {', '.join(item['ids'])}: {item['reason']}")
    return "\n".join(lines).rstrip() + "\n"


def main() -> None:
    ASSETS.mkdir(exist_ok=True)
    REPORTS.mkdir(exist_ok=True)
    payload, audit = build()
    OUT_JSON.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    OUT_AUDIT_JSON.write_text(json.dumps(audit, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    OUT_AUDIT_MD.write_text(render_md(audit), encoding="utf-8")
    print(
        f"input={audit['inputCount']} output={audit['outputCount']} "
        f"reduction={audit['reduction']} merges={audit['curatedMergeGroupCount']}"
    )
    print(f"wrote {OUT_JSON.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
