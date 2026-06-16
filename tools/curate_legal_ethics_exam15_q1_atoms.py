from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ATOM_FILE = ROOT / "assets" / "ox_legal_ethics_exam15.json"


Q1_ATOMS = [
    {
        "pid": "legal-ethics-r15-q01-01",
        "art": "변호사법 제90조",
        "artNo": 90,
        "topic": "징계의 종류",
        "rep": "변호사에 대한 징계는 영구제명, 제명, 3년 이하의 정직, 3천만원 이하의 과태료, 견책의 다섯 종류이다.",
        "why": "변호사법 제90조는 변호사 징계를 다섯 종류로 정하고, 과태료 상한을 3천만원으로 정합니다.",
        "ref": "변호사법 제90조",
        "grade": "A+",
        "weight": 0.86,
        "twins": [
            {
                "q": "변호사에 대한 징계는 영구제명, 제명, 3년 이하의 정직, 1천만 원 이하의 과태료, 견책의 다섯 종류이다.",
                "trap": "과태료 상한 액수 함정",
                "why": "과태료 상한은 1천만 원이 아니라 3천만원입니다.",
                "corrected": "변호사에 대한 징계는 영구제명, 제명, 3년 이하의 정직, 3천만원 이하의 과태료, 견책의 다섯 종류이다.",
                "src": ["법윤15"],
                "weight": 0.86,
                "grade": "A+",
                "ref": "변호사법 제90조",
                "sourcePart": "②",
            }
        ],
    },
    {
        "pid": "legal-ethics-r15-q01-02",
        "art": "변호사법 제97조의3",
        "artNo": 97,
        "topic": "징계개시 청원권자",
        "rep": "의뢰인이나 의뢰인의 법정대리인ㆍ배우자ㆍ직계친족 또는 형제자매는 수임변호사나 법무법인 담당변호사에 대한 징계개시의 신청을 청원할 수 있다.",
        "why": "변호사법 제97조의3 제1항은 징계개시 청원권자를 의뢰인, 법정대리인, 배우자, 직계친족, 형제자매로 한정합니다.",
        "ref": "변호사법 제97조의3 제1항",
        "grade": "A+",
        "weight": 0.86,
        "twins": [
            {
                "q": "의뢰인의 동거인도 수임변호사나 법무법인 담당변호사에 대한 징계개시의 신청을 청원할 수 있다.",
                "trap": "동거인 포함 여부 함정",
                "why": "변호사법 제97조의3 제1항의 청원권자에는 동거인이 포함되지 않습니다.",
                "corrected": "징계개시의 신청을 청원할 수 있는 자는 의뢰인이나 의뢰인의 법정대리인ㆍ배우자ㆍ직계친족 또는 형제자매이고, 동거인은 포함되지 않는다.",
                "src": ["법윤15"],
                "weight": 0.86,
                "grade": "A+",
                "ref": "변호사법 제97조의3 제1항",
                "sourcePart": "①",
            }
        ],
    },
    {
        "pid": "legal-ethics-r15-q01-03",
        "art": "변호사법 제91조",
        "artNo": 91,
        "topic": "영구제명 사유",
        "rep": "변호사의 직무와 관련하여 2회 이상 금고 이상의 형을 선고받아 그 형이 확정된 경우는 영구제명의 사유가 되며, 집행유예를 선고받은 경우도 포함하고 과실범은 제외한다.",
        "why": "변호사법 제91조 제1항 제1호는 직무 관련 2회 이상 금고 이상의 형 확정을 영구제명 사유로 보면서, 집행유예는 포함하고 과실범은 제외합니다.",
        "ref": "변호사법 제91조 제1항 제1호",
        "grade": "A+",
        "weight": 0.86,
        "twins": [
            {
                "q": "변호사의 직무와 관련하여 2회 이상 금고 이상의 형을 선고받아 그 형이 확정된 경우는 영구제명의 사유가 되나, 집행유예를 선고받은 경우와 과실범의 경우는 제외된다.",
                "trap": "집행유예 포함 여부 함정",
                "why": "집행유예를 선고받은 경우는 제외되는 것이 아니라 포함됩니다. 과실범만 제외됩니다.",
                "corrected": "변호사의 직무와 관련하여 2회 이상 금고 이상의 형을 선고받아 그 형이 확정된 경우는 영구제명의 사유가 되며, 집행유예를 선고받은 경우도 포함하고 과실범은 제외한다.",
                "src": ["법윤15"],
                "weight": 0.86,
                "grade": "A+",
                "ref": "변호사법 제91조 제1항 제1호",
                "sourcePart": "④",
            }
        ],
    },
    {
        "pid": "legal-ethics-r15-q01-04",
        "art": "변호사법 제98조의4",
        "artNo": 98,
        "topic": "징계 효력 발생 시점",
        "rep": "징계혐의자가 징계 결정의 통지를 받은 후 이의신청을 하지 아니하면 이의신청 기간이 끝난 날부터 변협징계위원회의 징계 효력이 발생한다.",
        "why": "변호사법 제98조의4 제3항은 징계 결정의 효력 발생 시점을 이의신청 기간이 끝난 날로 정합니다.",
        "ref": "변호사법 제98조의4 제3항",
        "grade": "A+",
        "weight": 0.86,
        "twins": [
            {
                "q": "대한변호사협회 변호사징계위원회의 징계에 관한 결정은 징계혐의자가 그 결정을 송달받은 날부터 효력이 발생한다.",
                "trap": "송달일과 효력 발생일 혼동",
                "why": "징계 결정은 송달받은 날부터 곧바로 효력이 발생하는 것이 아니라, 이의신청을 하지 않으면 이의신청 기간이 끝난 날부터 효력이 발생합니다.",
                "corrected": "징계혐의자가 징계 결정의 통지를 받은 후 이의신청을 하지 아니하면 이의신청 기간이 끝난 날부터 변협징계위원회의 징계 효력이 발생한다.",
                "src": ["법윤15"],
                "weight": 0.86,
                "grade": "A+",
                "ref": "변호사법 제98조의4 제3항",
                "sourcePart": "③",
            }
        ],
    },
]


def main() -> int:
    data = json.loads(ATOM_FILE.read_text(encoding="utf-8"))
    items = data.get("items", [])
    first_q1_index = next(
        (idx for idx, item in enumerate(items) if item.get("sourceQuestionId") == "legal_ethics_r15_q01"),
        None,
    )
    if first_q1_index is None:
        raise SystemExit("legal_ethics_r15_q01 atom not found")

    curated = []
    for idx, atom in enumerate(Q1_ATOMS, 1):
        row = {
            "src": ["법윤15"],
            "years": ["법윤15"],
            "freq": 1,
            "hot": False,
            "ids": [1],
            "xref": [],
            "subject": "법조윤리",
            "sourceQuestionId": "legal_ethics_r15_q01",
            "sourcePart": str(idx),
            "curation": {
                "status": "manual_curated",
                "date": "2026-06-17",
                "note": "제15회 1번을 보기 단위가 아니라 법리 단위 atom으로 분해함.",
            },
        }
        row.update(atom)
        curated.append(row)

    rest = [item for item in items if item.get("sourceQuestionId") != "legal_ethics_r15_q01"]
    data["items"] = rest[:first_q1_index] + curated + rest[first_q1_index:]
    data["count"] = len(data["items"])

    ATOM_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": "ok", "curated": "legal_ethics_r15_q01", "atoms": len(curated)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
