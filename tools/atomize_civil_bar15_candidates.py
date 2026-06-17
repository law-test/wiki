from __future__ import annotations

import csv
import json
import re
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "assets"
REPORTS = ROOT / "reports"
LEXBANK_PATTERN = "lex-bank_*_2026-06-16/02_export/mc_questions.csv"
ROUND_NO = 15
CIVIL_SUBJECT = "민사법"

CASE_PARTY_RE = re.compile(r"[甲乙丙丁戊己庚辛壬癸]|(?<![A-Za-z])[A-E](?![A-Za-z])")
QUESTION_RE = re.compile(r"[?？]|\?$")
MARKER_RE = re.compile(r"\|\s*\*\*(?P<marker>[ㄱ-ㅎ①-⑤])\.?\*\*.*?\|\s*(?P<ox>[✅❌○×OX])[^|]*\|\s*(?P<basis>.*?)\s*\|")
BULLET_RE = re.compile(
    r"^\s*[-*]\s*\*\*(?P<marker>[ㄱ-ㅎ①-⑤])\.?\s*(?:[○×OX]|[✅❌])?.*?\*\*\s*[—-]\s*(?P<basis>.+)$"
)
LAW_CASE_PREFIX_RE = re.compile(r"^(?:대법원|대판|헌재|서울[^—]{0,30}|민법|상법|민사소송법|어음법|주택임대차보호법|부동산실명법)[^—]{0,120}—\s*")


MANUAL_REP_OVERRIDES = {
    (2, "\u2463"): (
        "미등기건물 매수인은 등기를 마치지 않은 이상 소유권자가 아니므로 "
        "소유권에 기한 물권적 청구권을 행사할 수 없지만, 점유자라면 "
        "점유보호청구권은 행사할 수 있다."
    ),
    (2, "\u2464"): (
        "미등기건물 신축자가 토지를 점유·사용하다가 건물을 매도한 경우, "
        "그 신축자는 매도 후 점유를 상실하기 전까지의 기간에 대하여 "
        "토지소유자에게 부당이득반환의무를 부담할 수 있다."
    ),
    (6, "\u3131"): (
        "\ucc44\ubb34\uc790\uac00 \ub3d9\uc77c\ud55c \ucc44\uad8c \uc804\ubd80\uc5d0 \ub300\ud558\uc5ec "
        "\ucc44\ubb34\ub97c \uc2b9\uc778\ud558\uba74, \uadf8 \uc2b9\uc778\uc740 \ucc44\uad8c \uc804\ubd80\uc5d0 "
        "\ub300\ud55c \uc2dc\ud6a8\uc774\uc775 \ud3ec\uae30 \ub610\ub294 \uc2dc\ud6a8\uc911\ub2e8\uc758 "
        "\uc790\ub8cc\uac00 \ub420 \uc218 \uc788\ub2e4."
    ),
    (6, "\u3137"): (
        "임치물 반환청구권의 소멸시효는 임치계약 성립 시부터 진행하고, "
        "계약 해지 시부터 진행하는 것이 아니다."
    ),
    (7, "\u3131"): (
        "채무자가 목적 부동산에 관한 매매계약을 체결한 뒤 아직 소유권이전등기를 "
        "마치지 않은 경우에도, 그 부동산이 채무자의 책임재산에 해당하면 "
        "그 처분행위는 일반채권자에 대한 사해행위가 될 수 있다."
    ),
    (9, "\u3137"): (
        "소유권이전등기청구권은 채무자의 동의나 승낙이 없으면 양도하더라도 "
        "효력이 발생하지 않고, 이에 기초한 본등기도 무효이다."
    ),
    (9, "\u3139"): (
        "소유권이전등기에 적법한 원인행위가 있으면 등기절차상 합의가 "
        "흠결되었다는 사정만으로 그 등기가 무효가 되지는 않는다."
    ),
    (10, "\u3131"): (
        "공동저당의 목적물 중 채무자 소유 부동산과 물상보증인 소유 부동산이 "
        "함께 있는 경우, 채무자 소유 부동산이 그 가액 한도에서 "
        "피담보채권 전액을 먼저 부담한다."
    ),
    (10, "\u3137"): (
        "\ubb3c\uc0c1\ubcf4\uc99d\uc778 \uc18c\uc720 \ubd80\ub3d9\uc0b0\uc774 \uba3c\uc800 \uacbd\ub9e4\ub418\uc5b4 "
        "\uacf5\ub3d9\uc800\ub2f9\uad8c\uc790\uac00 \uc804\uc561\uc744 \ubcc0\uc81c\ubc1b\uc740 \uacbd\uc6b0, "
        "\uadf8 \ubd80\ub3d9\uc0b0\uc758 \ud6c4\uc21c\uc704\uc800\ub2f9\uad8c\uc790\ub294 \ubb3c\uc0c1\ubcf4\uc99d\uc778\uc744 "
        "\ub300\uc704\ud558\uc5ec \ucc44\ubb34\uc790 \uc18c\uc720 \ubd80\ub3d9\uc0b0\uc5d0 \uad00\ud55c "
        "\uc800\ub2f9\uad8c\uc774\uc804\uc758 \ubd80\uae30\ub4f1\uae30\ub97c \uccad\uad6c\ud560 \uc218 \uc788\ub2e4."
    ),
    (11, "\u3137"): (
        "채무자가 소송에서 응소하여 답변서를 제출하면 그 시점에 소멸시효가 "
        "중단되고, 나중에 시효중단 주장을 한 시점은 영향을 미치지 않는다."
    ),
    (13, "\u3131"): (
        "공유관계가 유지되는 일부 지분 양도는 토지와 건물의 소유자 분리가 "
        "아니므로 관습법상 법정지상권이 성립하지 않는다."
    ),
    (14, "\u3131"): (
        "연대보증인에게는 보통 보증인의 최고·검색의 항변권이 인정되지 않는다."
    ),
    (15, "\u3131"): (
        "상대방이 청약을 거절하면 청약의 효력은 확정적으로 소멸하고, "
        "그 뒤 번복하여 승낙하더라도 계약은 소급하여 성립하지 않는다."
    ),
    (16, "\u2461"): (
        "\ucde8\ub4dd\uc2dc\ud6a8 \uc644\uc131\uc790\ub294 \uc2dc\ud6a8\uc644\uc131 \ub2f9\uc2dc\uc758 "
        "\uc18c\uc720\uc790\uc5d0\uac8c \uc18c\uc720\uad8c\uc774\uc804\ub4f1\uae30\uccad\uad6c\uad8c\uc744 "
        "\uac00\uc9c8 \ubfd0\uc774\uace0, \ubb34\ud6a8\ub4f1\uae30 \uba85\uc758\uc790\ub97c \uc0c1\ub300\ub85c "
        "\uc9c1\uc811 \uc9c4\uc815\uba85\uc758\ud68c\ubcf5\uc744 \uc6d0\uc778\uc73c\ub85c \ud55c "
        "\uc18c\uc720\uad8c\uc774\uc804\ub4f1\uae30\ub97c \uccad\uad6c\ud560 \uc218\ub294 \uc5c6\ub2e4."
    ),
    (16, "\u2464"): (
        "\ucde8\ub4dd\uc2dc\ud6a8 \uc644\uc131\uc744 \uc6d0\uc778\uc73c\ub85c \ud55c \ub4f1\uae30\uccad\uad6c\uad8c\uc744 "
        "\ubcf4\uc804\ud558\uae30 \uc704\ud558\uc5ec, \uc2dc\ud6a8\uc644\uc131\uc790\ub294 \ub2f9\uc2dc "
        "\uc18c\uc720\uc790\ub97c \ub300\uc704\ud558\uc5ec \ubb34\ud6a8\uc778 \uba85\uc758\uc2e0\ud0c1 "
        "\ub4f1\uae30\uc758 \ub9d0\uc18c\ub97c \uccad\uad6c\ud560 \uc218 \uc788\ub2e4."
    ),
    (17, "\u3137"): (
        "\ucc44\uad8c\uc790\ub300\uc704\uc18c\uc1a1\uc5d0\uc11c \uc81c3\ucc44\ubb34\uc790\ub294 "
        "\ud53c\ubcf4\uc804\ucc44\uad8c\uc758 \ubc1c\uc0dd\uc6d0\uc778 \ubb34\ud6a8\ub098 "
        "\ubcc0\uc81c\uc18c\uba78\uc744 \uc8fc\uc7a5\ud558\uc5ec \ub300\uc704\uad8c \ud589\uc0ac\uc758 "
        "\uc801\ubc95\uc694\uac74\uc744 \ub2e4\ud23c \uc218 \uc788\uace0, \ubc95\uc6d0\ub3c4 "
        "\uc774\ub97c \uc9c1\uad8c\uc73c\ub85c \uc2ec\ub9ac\u00b7\ud310\ub2e8\ud558\uc5ec\uc57c \ud55c\ub2e4."
    ),
    (20, "\u3131"): (
        "\uc218\uc778\uc758 \ubb3c\uc0c1\ubcf4\uc99d\uc778\uc774 \uac01\uc790 \uc790\uae30 \uc18c\uc720 "
        "\ubd80\ub3d9\uc0b0\uc744 \uacf5\ub3d9\uc800\ub2f9\uc758 \ub2f4\ubcf4\ub85c \uc81c\uacf5\ud55c "
        "\ub4a4 \uadf8 \ubd80\ub3d9\uc0b0\uc774 \uc81c3\uc790\uc5d0\uac8c \uc591\ub3c4\ub41c \uacbd\uc6b0, "
        "\ubcc0\uc81c\ud55c \uc81c3\ucde8\ub4dd\uc790\ub294 \uac01 \ubd80\ub3d9\uc0b0 \uac00\uc561\uc5d0 "
        "\ube44\ub840\ud558\uc5ec \ub2e4\ub978 \uc81c3\ucde8\ub4dd\uc790\uc5d0 \ub300\ud558\uc5ec "
        "\ucc44\uad8c\uc790\ub97c \ub300\uc704\ud560 \uc218 \uc788\ub2e4."
    ),
    (20, "\u3134"): (
        "\uacf5\ub3d9\uc800\ub2f9\uc758 \ubaa9\uc801\ubb3c \uc911 \ucc44\ubb34\uc790 \uc18c\uc720 "
        "\ubd80\ub3d9\uc0b0\uacfc \ubb3c\uc0c1\ubcf4\uc99d\uc778 \uc18c\uc720 \ubd80\ub3d9\uc0b0\uc774 "
        "\uc11e\uc5ec \uc788\ub294 \uacbd\uc6b0, \ucc44\ubb34\uc790 \uc18c\uc720 \ubd80\ub3d9\uc0b0\uc774 "
        "\uadf8 \uac00\uc561 \ud55c\ub3c4\uc5d0\uc11c \ud53c\ub2f4\ubcf4\ucc44\uad8c \uc804\uc561\uc744 "
        "\uba3c\uc800 \ubd80\ub2f4\ud55c\ub2e4."
    ),
    (20, "\u3137"): (
        "\ubcf4\uc99d\uc778\uc774 \ubcc0\uc81c\ud558\uc5ec \ubc95\ub960\uc0c1 \ub2f9\uc5f0\ud788 "
        "\ucc44\uad8c\uc790\ub97c \ub300\uc704\ud558\ub294 \uacbd\uc6b0, \ucc44\ubb34\uc790 \uc18c\uc720 "
        "\ubd80\ub3d9\uc0b0\uc758 \uc81c3\ucde8\ub4dd\uc790\uc5d0 \ub300\ud558\uc5ec \ub300\uc704\uad8c\uc744 "
        "\ud589\uc0ac\ud558\ub294 \ub370 \ub300\uc704\uc758 \ubd80\uae30\ub4f1\uae30\ub294 \ud544\uc694\ud558\uc9c0 \uc54a\ub2e4."
    ),
    (24, "\u3137"): (
        "\uc591\ub3c4\uae08\uc9c0\ud2b9\uc57d\uc774 \uc788\ub294 \ucc44\uad8c\uc774\ub77c\ub3c4 "
        "\uc120\uc758\u00b7\ubb34\uc911\uacfc\uc2e4\uc758 \uc591\uc218\uc778\uc774 \uc801\ubc95\ud558\uac8c "
        "\ucde8\ub4dd\ud55c \ub4a4\uc5d0\ub294, \uc804\ub4dd\uc790\uc758 \uc545\uc758\u00b7\uc911\uacfc\uc2e4 "
        "\uc5ec\ubd80\uc640 \uad00\uacc4\uc5c6\uc774 \uc804\ub4dd\uc790\ub3c4 \uadf8 \ucc44\uad8c\uc744 "
        "\uc720\ud6a8\ud558\uac8c \ucde8\ub4dd\ud55c\ub2e4."
    ),
    (33, "\u2462"): (
        "\uce5c\uad8c\uc0c1\uc2e4\uc740 \uc601\uad6c\uc801 \ud6a8\uacfc\ub97c \uac00\uc9c0\ub294 "
        "\uc885\uad6d\uc801 \ucc98\ubd84\uc774\ubbc0\ub85c \uc77c\uc815 \uae30\uac04\uc744 \uc815\ud558\uc5ec "
        "\uc120\uace0\ud560 \uc218 \uc5c6\uace0, \uae30\uac04\uc744 \uc815\ud558\ub294 \uac83\uc740 "
        "\uce5c\uad8c \uc77c\uc2dc\uc815\uc9c0\uc758 \ubb38\uc81c\uc774\ub2e4."
    ),
    (36, "\u3134"): (
        "\ub2e8\ub3c5\ud310\uc0ac \uc0ac\uac74\uc758 \ud56d\uc18c\uc2ec \uacc4\uc18d \uc911 "
        "\ud569\uc758\ubd80 \uad00\ud560 \ubc18\uc18c\uac00 \uc81c\uae30\ub418\uc5c8\ub2e4\ub294 "
        "\uc0ac\uc815\ub9cc\uc73c\ub85c \ubcf8\uc18c\uc640 \ubc18\uc18c\uac00 \ub2f9\uc5f0\ud788 "
        "\uace0\ub4f1\ubc95\uc6d0\uc73c\ub85c \uc774\uc1a1\ub418\ub294 \uac83\uc740 \uc544\ub2c8\ub2e4."
    ),
    (44, "\u2460"): (
        "\uc8fc\uc8fc\ucd1d\ud68c\uacb0\uc758\uc758 \ud558\uc790\ub97c \ub2e4\ud22c\ub294 \uc18c\uc1a1\uc5d0\uc11c "
        "\uacb0\uc758 \ubd80\uc874\uc7ac\ub97c \ud655\uc778\ud558\ub294 \ub0b4\uc6a9\uc758 "
        "\uc7ac\ud310\uc0c1 \ud654\ud574\ub294 \uadf8 \uc131\uc9c8\uc0c1 \ud5c8\uc6a9\ub418\uc9c0 "
        "\uc54a\uc544 \ud654\ud574\uc870\uc11c\uc758 \ud6a8\ub825\uc774 \uc778\uc815\ub418\uc9c0 \uc54a\ub294\ub2e4."
    ),
    (44, "\u2461"): (
        "\uc18c\uc720\uad8c\uc5d0 \uae30\ud55c \uc18c\uc720\uad8c\uc774\uc804\ub4f1\uae30\ub9d0\uc18c\uccad\uad6c\uc18c\uc1a1\uc5d0\uc11c "
        "\ud654\ud574\uad8c\uace0\uacb0\uc815\uc774 \ud655\uc815\ub418\ub354\ub77c\ub3c4, \uadf8 "
        "\uccad\uad6c\uad8c\uc758 \ubb3c\uad8c\uc801 \uc131\uc9c8\uc774 \ucc44\uad8c\uc801 \uccad\uad6c\uad8c\uc73c\ub85c "
        "\ubc14\ub00c\uc9c0\ub294 \uc54a\ub294\ub2e4."
    ),
    (44, "\u2462"): (
        "\uc2e4\ud6a8\uc870\uac74\ubd80 \uc7ac\ud310\uc0c1 \ud654\ud574\uc5d0\uc11c \uc57d\uc815\ud55c "
        "\uc758\ubb34\uac00 \uc774\ud589\ub418\uc9c0 \uc54a\uc73c\uba74, \ud654\ud574\uc758 \ud6a8\ub825\uc740 "
        "\uc2e4\ud6a8\uc870\uac74 \uc131\ucde8\ub85c \uc18c\uba78\ud558\uace0 \uadf8 \uc2e4\ud6a8\ub294 "
        "\uc18c\uc1a1 \uc678\uc5d0\uc11c\ub3c4 \uc8fc\uc7a5\ud560 \uc218 \uc788\ub2e4."
    ),
    (44, "\u2463"): (
        "\uc7ac\ud310\uc0c1 \ud654\ud574\uc5d0 \ub530\ub978 \uc758\ubb34\uac00 \uc774\ud589\ub418\uc9c0 "
        "\uc54a\uc558\ub2e4\ub294 \uc774\uc720\ub9cc\uc73c\ub85c \ub2f9\uc0ac\uc790\uac00 \uadf8 "
        "\ud654\ud574\ub97c \ud574\uc81c\ud558\uc5ec \ud654\ud574\uc870\uc11c\uc758 \ucde8\uc9c0\uc5d0 "
        "\ubc18\ud558\ub294 \uc8fc\uc7a5\uc744 \ud560 \uc218\ub294 \uc5c6\ub2e4."
    ),
    (44, "\u2464"): (
        "\uc18c\uc1a1\uc774 \ud654\ud574\uad8c\uace0\uacb0\uc815\uc73c\ub85c \uc885\ub8cc\ub418\uc5c8\ub354\ub77c\ub3c4, "
        "\ubcf4\uc870\ucc38\uac00\uc778\uc774 \ud53c\ucc38\uac00\uc778\uc744 \ubcf4\uc870\ud558\uc5ec "
        "\uacf5\ub3d9\uc73c\ub85c \uc18c\uc1a1\uc744 \uc218\ud589\ud558\uc600\ub2e4\uba74 "
        "\ucc38\uac00\uc801 \ud6a8\ub825\uc774 \ubc1c\uc0dd\ud560 \uc218 \uc788\ub2e4."
    ),
}


def clean_text(value: str) -> str:
    value = value or ""
    value = re.sub(r"<[^>]+>", "", value)
    value = value.replace("&nbsp;", " ")
    value = re.sub(r"\*\*|`|>", "", value)
    value = value.replace("「", "").replace("」", "")
    value = value.replace("｢", "").replace("｣", "")
    value = re.sub(r"\[(.*?)\]\([^)]+\)", r"\1", value)
    value = re.sub(r"\s+", " ", value)
    return value.strip()


def find_lexbank_csv() -> Path:
    matches = list(Path(r"C:\cowork").glob(LEXBANK_PATTERN))
    if not matches:
        raise FileNotFoundError("lex-bank mc_questions.csv not found")
    return matches[0]


def load_lexbank_rows() -> dict[int, dict[str, str]]:
    path = find_lexbank_csv()
    rows: dict[int, dict[str, str]] = {}
    with path.open(encoding="utf-8-sig", newline="") as file:
        for row in csv.DictReader(file):
            if row.get("round") == str(ROUND_NO) and row.get("subject") == CIVIL_SUBJECT:
                rows[int(row["number"])] = row
    return rows


def extract_basis_map(ai_explanation: str) -> dict[str, str]:
    section = ai_explanation or ""
    idx = section.find("각 지문")
    if idx >= 0:
        section = section[idx:]
    out: dict[str, str] = {}
    for line in section.splitlines():
        line = line.strip()
        match = MARKER_RE.search(line) if line.startswith("|") else BULLET_RE.search(line)
        if not match:
            continue
        marker = match.group("marker")
        basis = clean_text(match.group("basis"))
        if basis:
            out[marker] = basis
    return out


def sentence_split(text: str) -> list[str]:
    parts = re.split(r"(?<=[다음임함됨됨다])\.\s+|(?<=다)\.\s+", text)
    cleaned = []
    for part in parts:
        part = part.strip()
        if not part:
            continue
        if not part.endswith(".") and part[-1] in "다음함됨임":
            part += "."
        cleaned.append(part)
    return cleaned


def normalize_principle(raw_basis: str, fallback: str, answer: str) -> tuple[str, list[str], list[str]]:
    flags: list[str] = []
    info_tags: list[str] = []
    text = clean_text(raw_basis)
    if not text:
        text = clean_text(fallback)
        flags.append("basis_missing_source_fallback")

    text = re.sub(r"^(?:틀림|맞음|옳음|정답)\.?\s*", "", text)
    text = re.sub(r"^\*\*틀림\.\*\*\s*", "", text)
    text = LAW_CASE_PREFIX_RE.sub("", text)
    text = re.sub(r"^\(?[ㄱ-ㅎ①-⑤]\)?\s*", "", text)
    text = re.sub(r"\([^)]*[甲乙丙丁戊己庚辛壬癸][^)]*\)", "", text)
    text = re.sub(r"\s+", " ", text).strip()

    # Prefer the explanatory rule before fact-specific "따라서 ..." conclusions.
    text = re.split(r"\s+따라서\s+", text)[0].strip()
    text = re.split(r"\s+즉\s+", text)[0].strip()

    replacements = {
        "안 됨": "적용되지 않는다",
        "소멸 X": "소멸하지 않는다",
        "소멸 O": "소멸한다",
        "취득 불가": "취득할 수 없다",
        "행사 불가": "행사할 수 없다",
        "청구 불가": "청구할 수 없다",
        "인정 X": "인정되지 않는다",
        "대항 불가": "대항할 수 없다",
        "보호 X": "보호되지 않는다",
    }
    for before, after in replacements.items():
        text = text.replace(before, after)

    # Remove obvious case party labels that remain in source explanations.
    text = re.sub(r"[甲乙丙丁戊己庚辛壬癸]\s*(?:은|는|이|가|에게|을|를|의|과|와)", "", text)
    text = re.sub(r"\b[A-E]\s*(?:회사|주식회사|은행|조합|공사|토지|건물|채권|주식)?", lambda m: m.group(0).replace(m.group(0)[0], "").strip(), text)
    text = re.sub(r"\s+", " ", text).strip(" .")

    if text and not text.endswith(("다", "다.", "된다", "된다.", "없다", "없다.", "있다", "있다.")):
        if text.endswith("가능"):
            text = text[:-2].rstrip() + "할 수 있다"
        elif text.endswith("불가"):
            text = text[:-2].rstrip() + "할 수 없다"
    if text and not text.endswith("."):
        text += "."

    if CASE_PARTY_RE.search(text):
        flags.append("case_party_remains")
    if QUESTION_RE.search(text):
        flags.append("question_form")
    if len(text) < 18:
        flags.append("too_short")
    if len(sentence_split(text)) > 2:
        flags.append("possibly_multiple_principles")
    if answer == "X" and "틀림" in raw_basis:
        info_tags.append("corrected_from_false_source")
    return text, flags, info_tags


def first_ref(value: str) -> str:
    refs = [part.strip() for part in (value or "").split(",") if part.strip()]
    return refs[0] if refs else ""


def build_candidates() -> tuple[dict[str, Any], dict[str, Any]]:
    source = json.loads((ASSETS / "ox_civil_bar15.json").read_text(encoding="utf-8"))
    rows = load_lexbank_rows()
    basis_by_question = {
        number: extract_basis_map(row.get("ai_explanation") or "")
        for number, row in rows.items()
    }

    candidates: list[dict[str, Any]] = []
    for item in source["items"]:
        q_no = int(item["question_no"])
        marker = item["choice"]
        basis = basis_by_question.get(q_no, {}).get(marker, "")
        principle, flags, info_tags = normalize_principle(basis, item["q"], item["a"])
        manual_rep = MANUAL_REP_OVERRIDES.get((q_no, marker))
        if manual_rep:
            principle = manual_rep
            flags = []
            info_tags.append("manual_override")
        pid = f"civil-bar15-q{q_no:02d}-{marker}"
        candidates.append(
            {
                "pid": pid,
                "round": ROUND_NO,
                "year": item["year"],
                "subject": item["subject"],
                "topic": item.get("topic") or "",
                "rep": principle,
                "a": "O",
                "why": principle,
                "ref": item.get("ref") or "",
                "art": item.get("art") or "",
                "src": item.get("src") or [],
                "refs": item.get("refs") or [],
                "grade": "A" if not flags else "검수",
                "weight": 0.8 if not flags else 0.4,
                "source_answer": item["a"],
                "source_statement": item["q"],
                "source_basis": basis,
                "source_layer_needs_atomization": bool(item.get("needs_atomization")),
                "quality_flags": flags,
                "info_tags": info_tags,
                "twins": [],
                "type": "civil_bar_minimal_atom_draft",
            }
        )

    by_subject = Counter(item["subject"] for item in candidates)
    by_flag = Counter(flag for item in candidates for flag in item["quality_flags"])
    by_info = Counter(tag for item in candidates for tag in item["info_tags"])
    high_confidence = [item for item in candidates if not item["quality_flags"]]
    needs_review = [item for item in candidates if item["quality_flags"]]

    payload = {
        "title": "제15회 변호사시험 민사법 최소 원리 atom 초안",
        "round": ROUND_NO,
        "year": 2026,
        "source": "assets/ox_civil_bar15.json + lex-bank explanation basis transformed into principle candidates",
        "updatedAt": datetime.now(timezone.utc).isoformat(),
        "count": len(candidates),
        "highConfidenceCount": len(high_confidence),
        "needsReviewCount": len(needs_review),
        "subjectCounts": dict(by_subject),
        "flagCounts": dict(by_flag),
        "infoTagCounts": dict(by_info),
        "items": candidates,
    }
    audit = {
        "count": len(candidates),
        "subjectCounts": dict(by_subject),
        "flagCounts": dict(by_flag),
        "infoTagCounts": dict(by_info),
        "highConfidenceCount": len(high_confidence),
        "needsReviewCount": len(needs_review),
        "needsReviewBySubject": dict(Counter(item["subject"] for item in needs_review)),
        "remainingCaseParty": [
            {"src": item["src"], "rep": item["rep"], "subject": item["subject"]}
            for item in needs_review
            if "case_party_remains" in item["quality_flags"]
        ],
        "samples": candidates[:12],
    }
    return payload, audit


def write_json(path: Path, data: Any) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def render_report(payload: dict[str, Any], audit: dict[str, Any]) -> str:
    lines: list[str] = []
    lines.append("# 제15회 민사법 최소 원리 atom 초안 검증")
    lines.append("")
    lines.append("- 기준: `assets/ox_civil_bar15.json` + lex-bank 해설의 각 지문 검토")
    lines.append("- 작성일: 2026-06-17")
    lines.append("")
    lines.append("## 결론")
    lines.append("")
    lines.append(f"- 초안 atom: {payload['count']}개")
    lines.append(f"- 자동 통과: {payload['highConfidenceCount']}개")
    lines.append(f"- 검수 필요: {payload['needsReviewCount']}개")
    lines.append(
        "- 과목: "
        + " / ".join(f"{k} {v}개" for k, v in payload["subjectCounts"].items())
    )
    lines.append("")
    lines.append("## 검수 플래그")
    lines.append("")
    if payload["flagCounts"]:
        for flag, count in payload["flagCounts"].items():
            lines.append(f"- {flag}: {count}개")
    else:
        lines.append("- 없음")
    lines.append("")
    if payload.get("infoTagCounts"):
        lines.append("## 정보 태그")
        lines.append("")
        for tag, count in payload["infoTagCounts"].items():
            lines.append(f"- {tag}: {count}개")
        lines.append("")
    lines.append("## 잔여 사례 인물")
    lines.append("")
    remaining = audit["remainingCaseParty"]
    if not remaining:
        lines.append("- 없음")
    else:
        for row in remaining[:40]:
            lines.append(f"- {row['src'][0] if row['src'] else '-'} / {row['subject']}: {row['rep']}")
    lines.append("")
    lines.append("## 샘플")
    lines.append("")
    for item in payload["items"][:20]:
        flags = ", ".join(item["quality_flags"]) if item["quality_flags"] else "통과"
        lines.append(f"- {item['src'][0] if item['src'] else item['pid']} [{flags}] {item['rep']}")
    lines.append("")
    lines.append("## 다음 단계")
    lines.append("")
    lines.append("1. 검수 필요 atom을 사람 눈으로 다시 고쳐 확정본을 만든다.")
    lines.append("2. 확정본에서 동일 법리 중복을 합치고, X 쌍둥이 atom을 별도로 붙인다.")
    lines.append("3. `assets/ox_msa_unified_v001.json` 통합본에 병합한다.")
    lines.append("")
    return "\n".join(lines)


def main() -> None:
    payload, audit = build_candidates()
    write_json(ASSETS / "ox_civil_bar15_minimal_atoms_draft.json", payload)
    REPORTS.mkdir(exist_ok=True)
    write_json(REPORTS / "civil_bar15_minimal_atom_audit.json", audit)
    (REPORTS / "civil_bar15_minimal_atom_audit.md").write_text(
        render_report(payload, audit),
        encoding="utf-8",
    )
    print(
        "items={count} high={high} review={review}".format(
            count=payload["count"],
            high=payload["highConfidenceCount"],
            review=payload["needsReviewCount"],
        )
    )


if __name__ == "__main__":
    main()
