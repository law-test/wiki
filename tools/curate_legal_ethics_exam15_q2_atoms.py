from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ATOM_FILE = ROOT / "assets" / "ox_legal_ethics_exam15.json"


Q2_ATOMS = [
    {
        "pid": "legal-ethics-r15-q02-01",
        "art": "변호사법 제5조, 제18조",
        "artNo": 5,
        "topic": "영구제명과 징계대상성",
        "rep": "변호사법상 이 법에 따라 영구제명된 자는 변호사가 될 수 없으므로, 영구제명 후의 행위는 변호사에 대한 징계절차의 대상이 아니라 무자격 법률사무 취급 등 별도 문제로 다루어진다.",
        "why": "영구제명된 자는 변호사 결격사유에 해당하므로 변호사 신분을 전제로 하는 징계대상성과 구별해야 합니다.",
        "ref": "변호사법 제5조 제10호, 제18조",
        "grade": "A",
        "weight": 0.78,
        "twins": [
            {
                "q": "변호사법상 영구제명된 자가 다시 법률사무를 처리하면 그 후의 행위도 변호사징계위원회의 징계 대상이 된다.",
                "trap": "영구제명 후 신분 전제 혼동",
                "why": "영구제명은 변호사 결격사유이므로 변호사 신분을 전제로 한 징계절차의 대상성과 구별됩니다.",
                "corrected": "변호사법상 이 법에 따라 영구제명된 자는 변호사가 될 수 없으므로, 영구제명 후의 행위는 변호사에 대한 징계절차의 대상이 아니라 무자격 법률사무 취급 등 별도 문제로 다루어진다.",
            }
        ],
    },
    {
        "pid": "legal-ethics-r15-q02-02",
        "art": "변호사법 제5조, 제18조",
        "artNo": 18,
        "topic": "실형 확정과 등록취소",
        "rep": "변호사법상 금고 이상의 실형이 확정되어 결격사유가 발생한 경우에는 변호사 등록취소가 문제되며, 이를 곧바로 변호사 징계대상 사안으로만 처리하지 않는다.",
        "why": "금고 이상의 실형 확정은 변호사 결격사유와 등록취소 사유가 되므로 징계사유 판단과 구별해야 합니다.",
        "ref": "변호사법 제5조 제1호, 제18조",
        "grade": "A",
        "weight": 0.76,
        "twins": [
            {
                "q": "변호사법상 금고 이상의 실형이 확정된 경우에도 변호사 등록취소와 무관하게 언제나 변호사 징계대상으로만 처리된다.",
                "trap": "등록취소 사유와 징계사유 혼동",
                "why": "금고 이상의 실형 확정은 먼저 결격사유와 등록취소 사유로 보아야 합니다.",
                "corrected": "변호사법상 금고 이상의 실형이 확정되어 결격사유가 발생한 경우에는 변호사 등록취소가 문제되며, 이를 곧바로 변호사 징계대상 사안으로만 처리하지 않는다.",
            }
        ],
    },
    {
        "pid": "legal-ethics-r15-q02-03",
        "art": "변호사법 제24조, 제91조",
        "artNo": 24,
        "topic": "직무 외 품위손상",
        "rep": "변호사법상 직무 외 행위도 변호사의 품위를 손상하면 징계사유가 될 수 있다.",
        "why": "변호사법 제91조 제2항은 직무의 내외를 막론하고 변호사로서의 품위를 손상하는 행위를 징계사유로 봅니다.",
        "ref": "변호사법 제24조 제1항, 제91조 제2항 제3호",
        "grade": "A+",
        "weight": 0.84,
        "twins": [
            {
                "q": "변호사법상 품위유지의무 위반은 변호사의 직무수행과 직접 관련된 행위에 한정된다.",
                "trap": "직무 내 행위로 한정",
                "why": "품위손상 징계사유는 직무의 내외를 막론합니다.",
                "corrected": "변호사법상 직무 외 행위도 변호사의 품위를 손상하면 징계사유가 될 수 있다.",
            }
        ],
    },
    {
        "pid": "legal-ethics-r15-q02-04",
        "art": "변호사법 제24조, 제91조",
        "artNo": 91,
        "topic": "형사 무죄와 징계",
        "rep": "변호사법상 형사사건에서 무죄판결이 확정되었다는 사정만으로 같은 사실관계에 관한 품위손상 징계사유가 당연히 부정되는 것은 아니다.",
        "why": "형사책임과 변호사 징계책임은 판단 목적과 기준이 다르므로 무죄판결만으로 품위손상 징계사유가 당연히 사라지지는 않습니다.",
        "ref": "변호사법 제24조 제1항, 제91조 제2항 제3호",
        "grade": "A",
        "weight": 0.8,
        "twins": [
            {
                "q": "변호사법상 형사사건에서 무죄판결이 확정되면 같은 사실관계에 관한 변호사 징계사유도 당연히 부정된다.",
                "trap": "형사책임과 징계책임 동일시",
                "why": "형사 무죄와 징계책임 부정은 자동으로 연결되지 않습니다.",
                "corrected": "변호사법상 형사사건에서 무죄판결이 확정되었다는 사정만으로 같은 사실관계에 관한 품위손상 징계사유가 당연히 부정되는 것은 아니다.",
            }
        ],
    },
    {
        "pid": "legal-ethics-r15-q02-05",
        "art": "변호사법 제24조, 제91조",
        "artNo": 24,
        "topic": "사무직원 감독책임",
        "rep": "변호사는 사무직원의 업무처리를 지휘·감독할 책임이 있고, 사무직원의 과실로 의뢰인에게 절차상 불이익이 발생한 경우 징계사유가 될 수 있다.",
        "why": "변호사의 직무수행 책임에는 사무직원 감독도 포함되므로 단순히 사무직원의 과실이라는 이유만으로 징계책임이 배제되지는 않습니다.",
        "ref": "변호사법 제24조 제1항, 제91조 제2항 제1호·제3호",
        "grade": "A",
        "weight": 0.78,
        "twins": [
            {
                "q": "변호사법상 사무직원의 과실로 의뢰인에게 절차상 불이익이 발생한 경우 담당 변호사는 징계책임을 지지 않는다.",
                "trap": "사무직원 과실로 책임 배제",
                "why": "사무직원의 과실이더라도 변호사의 감독책임이 문제될 수 있습니다.",
                "corrected": "변호사는 사무직원의 업무처리를 지휘·감독할 책임이 있고, 사무직원의 과실로 의뢰인에게 절차상 불이익이 발생한 경우 징계사유가 될 수 있다.",
            }
        ],
    },
]


def main() -> int:
    data = json.loads(ATOM_FILE.read_text(encoding="utf-8"))
    items = data.get("items", [])
    first_q2_index = next(
        (idx for idx, item in enumerate(items) if item.get("sourceQuestionId") == "legal_ethics_r15_q02"),
        None,
    )
    if first_q2_index is None:
        raise SystemExit("legal_ethics_r15_q02 atom not found")

    curated = []
    for idx, atom in enumerate(Q2_ATOMS, 1):
        row = {
            "src": ["법윤15"],
            "years": ["법윤15"],
            "freq": 1,
            "hot": False,
            "ids": [2],
            "xref": [],
            "subject": "법조윤리",
            "sourceQuestionId": "legal_ethics_r15_q02",
            "sourcePart": str(idx),
            "curation": {
                "status": "manual_curated",
                "date": "2026-06-17",
                "note": "15회 2번을 사례 문장이 아니라 이름 없는 최소 법리 atom으로 재작성함.",
            },
        }
        row.update(atom)
        for twin in row.get("twins", []):
            twin.setdefault("src", ["법윤15"])
            twin.setdefault("weight", row["weight"])
            twin.setdefault("grade", row["grade"])
            twin.setdefault("ref", row["ref"])
            twin.setdefault("sourcePart", str(idx))
        curated.append(row)

    rest = [item for item in items if item.get("sourceQuestionId") != "legal_ethics_r15_q02"]
    data["items"] = rest[:first_q2_index] + curated + rest[first_q2_index:]
    data["count"] = len(data["items"])

    ATOM_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": "ok", "curated": "legal_ethics_r15_q02", "atoms": len(curated)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
