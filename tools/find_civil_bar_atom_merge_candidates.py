from __future__ import annotations

import difflib
import itertools
import json
import re
from collections import Counter, defaultdict, deque
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "assets"
REPORTS = ROOT / "reports"
INPUT = ASSETS / "ox_msa_bar_exam_integrated_draft_v001.json"
OUT_JSON = REPORTS / "civil_bar_atom_merge_candidates.json"
OUT_MD = REPORTS / "civil_bar_atom_merge_candidates.md"

SOURCE_RE = re.compile(r"\ubcc0\uc2dc(\d+)\s+(\d+)\ubc88")
REMOVE_TOKENS = [
    "○",
    "✗",
    "×",
    "X",
    "x",
    "O",
    "\uc815\ub2f5",
    "\ud568\uc815",
    "\ub300\ud45c",
    "\uae30\ucd9c",
    "—",
    "ㆍ",
    "·",
    "-",
]


def clean_text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def norm_text(value: str) -> str:
    text = re.sub(r"\([^)]*\)", " ", str(value or ""))
    for token in REMOVE_TOKENS:
        text = text.replace(token, " ")
    return "".join(ch for ch in text if ch.isalnum())


def ngrams(value: str, size: int = 3) -> set[str]:
    if not value:
        return set()
    if len(value) <= size:
        return {value}
    return {value[index : index + size] for index in range(len(value) - size + 1)}


def similarity(left: str, right: str) -> tuple[float, float, float]:
    left_norm = norm_text(left)
    right_norm = norm_text(right)
    if not left_norm or not right_norm:
        return 0.0, 0.0, 0.0
    left_grams = ngrams(left_norm)
    right_grams = ngrams(right_norm)
    jaccard = len(left_grams & right_grams) / len(left_grams | right_grams)
    sequence = difflib.SequenceMatcher(None, left_norm, right_norm).ratio()
    score = 0.55 * sequence + 0.45 * jaccard
    return round(score, 4), round(sequence, 4), round(jaccard, 4)


def source_questions(item: dict[str, Any]) -> set[tuple[int, int]]:
    out: set[tuple[int, int]] = set()
    for label in item.get("src") or []:
        match = SOURCE_RE.search(str(label))
        if match:
            out.add((int(match.group(1)), int(match.group(2))))
    return out


def pair_key(left_index: int, right_index: int) -> tuple[int, int]:
    return (left_index, right_index) if left_index < right_index else (right_index, left_index)


def source_text(item: dict[str, Any]) -> str:
    return " · ".join(clean_text(value) for value in item.get("src") or [] if clean_text(value))


def make_pair(
    items: list[dict[str, Any]],
    left_index: int,
    right_index: int,
    modes: set[str],
    kind: str,
) -> dict[str, Any]:
    left = items[left_index]
    right = items[right_index]
    score, sequence, jaccard = similarity(left.get("rep") or "", right.get("rep") or "")
    return {
        "kind": kind,
        "score": score,
        "sequence": sequence,
        "jaccard": jaccard,
        "modes": sorted(modes),
        "sameArticle": bool(left.get("art") and left.get("art") == right.get("art")),
        "sameTopic": bool(left.get("topic") and left.get("topic") == right.get("topic")),
        "left": {
            "pid": left.get("pid"),
            "subject": left.get("subject"),
            "answer": left.get("a"),
            "art": left.get("art"),
            "topic": left.get("topic"),
            "src": left.get("src") or [],
            "sourceText": source_text(left),
            "rep": clean_text(left.get("rep") or ""),
        },
        "right": {
            "pid": right.get("pid"),
            "subject": right.get("subject"),
            "answer": right.get("a"),
            "art": right.get("art"),
            "topic": right.get("topic"),
            "src": right.get("src") or [],
            "sourceText": source_text(right),
            "rep": clean_text(right.get("rep") or ""),
        },
    }


def collect_candidate_pairs(items: list[dict[str, Any]], conflict: bool = False) -> list[dict[str, Any]]:
    pair_modes: dict[tuple[int, int], set[str]] = defaultdict(set)
    bucket_fields = ("art", "topic")

    for field in bucket_fields:
        buckets: dict[tuple[str, str], list[int]] = defaultdict(list)
        for index, item in enumerate(items):
            value = clean_text(item.get(field) or "")
            if not value:
                continue
            answer_key = "*" if conflict else clean_text(item.get("a") or "")
            buckets[(clean_text(item.get("subject") or ""), answer_key, value)].append(index)

        for bucket in buckets.values():
            if len(bucket) <= 1 or len(bucket) > 220:
                continue
            for left_index, right_index in itertools.combinations(bucket, 2):
                left = items[left_index]
                right = items[right_index]
                if conflict:
                    if left.get("a") == right.get("a"):
                        continue
                elif left.get("a") != right.get("a"):
                    continue
                if source_questions(left) & source_questions(right):
                    continue
                pair_modes[pair_key(left_index, right_index)].add(field)

    pairs: list[dict[str, Any]] = []
    for (left_index, right_index), modes in pair_modes.items():
        score, _, jaccard = similarity(items[left_index].get("rep") or "", items[right_index].get("rep") or "")
        if conflict:
            keep = score >= 0.58 or ("art" in modes and score >= 0.52 and jaccard >= 0.26)
            kind = "possible_ox_conflict"
        else:
            keep = score >= 0.62 or ("art" in modes and score >= 0.55 and jaccard >= 0.28)
            kind = "possible_merge"
        if keep:
            pairs.append(make_pair(items, left_index, right_index, modes, kind))

    pairs.sort(key=lambda pair: pair["score"], reverse=True)
    return pairs


def connected_clusters(pairs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    graph: dict[str, set[str]] = defaultdict(set)
    by_pid: dict[str, dict[str, Any]] = {}
    for pair in pairs:
        left = pair["left"]
        right = pair["right"]
        left_pid = str(left["pid"])
        right_pid = str(right["pid"])
        graph[left_pid].add(right_pid)
        graph[right_pid].add(left_pid)
        by_pid[left_pid] = left
        by_pid[right_pid] = right

    visited: set[str] = set()
    clusters: list[dict[str, Any]] = []
    for start in sorted(graph):
        if start in visited:
            continue
        queue: deque[str] = deque([start])
        visited.add(start)
        nodes: list[str] = []
        while queue:
            node = queue.popleft()
            nodes.append(node)
            for next_node in graph[node]:
                if next_node not in visited:
                    visited.add(next_node)
                    queue.append(next_node)
        cluster_pairs = [
            pair
            for pair in pairs
            if pair["left"]["pid"] in nodes and pair["right"]["pid"] in nodes
        ]
        clusters.append(
            {
                "size": len(nodes),
                "pairCount": len(cluster_pairs),
                "maxScore": max(pair["score"] for pair in cluster_pairs),
                "items": [by_pid[node] for node in sorted(nodes)],
            }
        )
    clusters.sort(key=lambda cluster: (cluster["maxScore"], cluster["size"]), reverse=True)
    return clusters


def build() -> dict[str, Any]:
    data = json.loads(INPUT.read_text(encoding="utf-8"))
    items = list(data.get("items") or [])
    merge_pairs = collect_candidate_pairs(items, conflict=False)
    conflict_pairs = collect_candidate_pairs(items, conflict=True)
    clusters = connected_clusters(merge_pairs)
    return {
        "title": "변호사시험 민사법 atom 유사 병합 후보",
        "builtAt": datetime.now(timezone.utc).isoformat(),
        "source": f"assets/{INPUT.name}",
        "sourceCount": len(items),
        "mergeCandidateCount": len(merge_pairs),
        "conflictCandidateCount": len(conflict_pairs),
        "clusterCount": len(clusters),
        "mergeCandidates": merge_pairs,
        "conflictCandidates": conflict_pairs,
        "clusters": clusters,
    }


def render_pair(pair: dict[str, Any], index: int) -> list[str]:
    left = pair["left"]
    right = pair["right"]
    mode = ", ".join(pair["modes"])
    return [
        f"### {index}. {pair['kind']} · score {pair['score']:.3f} · {mode}",
        f"- 과목/정답: {left['subject']} / {left['answer']} ↔ {right['answer']}",
        f"- 조문/주제: {left.get('art') or '-'} / {left.get('topic') or '-'}",
        f"- A 출처: {left['sourceText']}",
        f"- A 문장: {left['rep']}",
        f"- B 출처: {right['sourceText']}",
        f"- B 문장: {right['rep']}",
        "",
    ]


def render_md(data: dict[str, Any]) -> str:
    merge_pairs = data["mergeCandidates"]
    conflict_pairs = data["conflictCandidates"]
    subject_counts = Counter(pair["left"]["subject"] for pair in merge_pairs)
    lines = [
        "# 변호사시험 민사법 atom 유사 병합 후보",
        "",
        f"- 기준 파일: `{data['source']}`",
        f"- 기준 atom: {data['sourceCount']:,}개",
        f"- 병합 후보 쌍: {data['mergeCandidateCount']:,}개",
        f"- 병합 후보 묶음: {data['clusterCount']:,}개",
        f"- O/X 충돌 의심 쌍: {data['conflictCandidateCount']:,}개",
        "",
        "## 읽는 법",
        "",
        "- 같은 문제 안의 선택지끼리는 제외했습니다.",
        "- 같은 과목·같은 O/X·같은 조문 또는 같은 주제 안에서 문장 유사도가 높은 것을 병합 후보로 잡았습니다.",
        "- O/X가 서로 다른데 문장이 비슷한 것은 병합하지 말고, 정답·표현 오류 가능성 후보로 따로 분리했습니다.",
        "- 이 보고서는 자동 병합 결과가 아니라 사람 검토용 후보 목록입니다.",
        "",
        "## 과목별 병합 후보",
        "",
    ]
    for subject, count in subject_counts.most_common():
        lines.append(f"- {subject}: {count:,}쌍")
    lines.extend(["", "## 병합 후보 상위", ""])
    if not merge_pairs:
        lines.append("- 후보 없음")
    for index, pair in enumerate(merge_pairs[:80], start=1):
        lines.extend(render_pair(pair, index))

    lines.extend(["", "## O/X 충돌 의심 후보", ""])
    if not conflict_pairs:
        lines.append("- 후보 없음")
    for index, pair in enumerate(conflict_pairs[:80], start=1):
        lines.extend(render_pair(pair, index))
    return "\n".join(lines).rstrip() + "\n"


def main() -> None:
    REPORTS.mkdir(exist_ok=True)
    data = build()
    OUT_JSON.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    OUT_MD.write_text(render_md(data), encoding="utf-8")
    print(
        f"source={data['sourceCount']} mergeCandidates={data['mergeCandidateCount']} "
        f"clusters={data['clusterCount']} conflicts={data['conflictCandidateCount']}"
    )
    print(f"wrote {OUT_MD.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
