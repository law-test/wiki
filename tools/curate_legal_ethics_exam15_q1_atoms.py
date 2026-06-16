from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ATOM_FILE = ROOT / "assets" / "ox_legal_ethics_exam15.json"


Q1_REP = (
    "수임변호사나 법무법인의 담당변호사에 대한 징계개시의 신청을 청원할 수 있는 자는 "
    "의뢰인이나 의뢰인의 법정대리인, 배우자, 직계친족 또는 형제자매이며, 동거인은 포함되지 않는다."
)

Q1_REF = (
    "변호사법 제90조 · 변호사법 제91조 · 변호사법 제97조의3 · "
    "변호사법 제98조의4 · 변호사법 제98조의5"
)

Q1_WHY = (
    "제15회 법조윤리시험 1번은 변호사 징계의 종류, 영구제명 사유, "
    "징계개시 청원권자, 징계 효력 발생 시점을 묻는 문제입니다."
)

Q1_TWINS = [
    {
        "q": "징계의 종류에는 영구제명, 제명, 3년 이하의 정직, 1천만 원 이하의 과태료, 견책이 있다.",
        "trap": "과태료 상한 액수 함정",
        "why": "변호사법 제90조의 과태료 상한은 1천만 원이 아니라 3천만원입니다. 정직 기간 3년 이하는 맞습니다.",
        "corrected": "징계의 종류에는 영구제명, 제명, 3년 이하의 정직, 3천만원 이하의 과태료, 견책이 있다.",
        "src": ["법윤15"],
        "weight": 0.86,
        "grade": "A+",
        "ref": "변호사법 제90조",
        "sourcePart": "②",
    },
    {
        "q": "대한변호사협회 변호사징계위원회의 징계에 관한 결정은 징계혐의자가 그 결정을 송달받은 날부터 효력이 발생한다.",
        "trap": "징계 효력 발생 시점 함정",
        "why": "변협징계위원회의 징계 결정은 송달일부터 곧바로 효력이 생기는 것이 아니라, 징계혐의자가 이의신청을 하지 않으면 이의신청 기간이 끝난 날부터 효력이 발생합니다.",
        "corrected": "징계혐의자가 징계 결정의 통지를 받은 후 이의신청을 하지 아니하면 이의신청 기간이 끝난 날부터 변협징계위원회의 징계 효력이 발생한다.",
        "src": ["법윤15"],
        "weight": 0.86,
        "grade": "A+",
        "ref": "변호사법 제98조의4 제3항",
        "sourcePart": "③",
    },
    {
        "q": "변호사의 직무와 관련하여 2회 이상 금고 이상의 형을 선고받아 그 형이 확정된 경우는 영구제명의 사유가 되나, 집행유예를 선고받은 경우와 과실범의 경우는 제외된다.",
        "trap": "영구제명 사유의 집행유예 포함 여부 함정",
        "why": "변호사법 제91조 제1항 제1호는 집행유예를 선고받은 경우를 포함한다고 정하고, 과실범만 제외합니다.",
        "corrected": "변호사의 직무와 관련하여 2회 이상 금고 이상의 형을 선고받아 그 형이 확정된 경우는 영구제명의 사유가 되며, 집행유예를 선고받은 경우를 포함하고 과실범은 제외한다.",
        "src": ["법윤15"],
        "weight": 0.86,
        "grade": "A+",
        "ref": "변호사법 제91조 제1항 제1호",
        "sourcePart": "④",
    },
]


def main() -> int:
    data = json.loads(ATOM_FILE.read_text(encoding="utf-8"))
    items = data.get("items", [])
    q1 = next((item for item in items if item.get("sourceQuestionId") == "legal_ethics_r15_q01"), None)
    if not q1:
        raise SystemExit("legal_ethics_r15_q01 atom not found")

    q1.update(
        {
            "art": "변호사법 제97조의3",
            "artNo": 97,
            "topic": "징계개시 청원",
            "rep": Q1_REP,
            "why": Q1_WHY,
            "ref": Q1_REF,
            "src": ["법윤15"],
            "years": ["법윤15"],
            "freq": 1,
            "hot": False,
            "twins": Q1_TWINS,
            "subject": "법조윤리",
            "weight": 0.86,
            "grade": "A+",
            "sourcePart": "①",
            "curation": {
                "status": "manual_curated",
                "date": "2026-06-17",
                "note": "오답 선지별 틀린 이유와 옳은 문장을 별도로 교정함.",
            },
        }
    )

    ATOM_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": "ok", "curated": q1["sourceQuestionId"], "twins": len(Q1_TWINS)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
