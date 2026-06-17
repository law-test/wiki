from __future__ import annotations

import csv
import argparse
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
SOURCE_ASSET_NAME = "ox_civil_bar15.json"
OUTPUT_ASSET_NAME = "ox_civil_bar15_minimal_atoms_draft.json"
REPORT_PREFIX = "civil_bar15_minimal_atom_audit"

CASE_PARTY_RE = re.compile(r"[甲乙丙丁戊己庚辛壬癸]|(?<![A-Za-z])[A-E](?![A-Za-z])|(?<![A-Za-z])[X-Z](?![A-Za-z])")
QUESTION_RE = re.compile(r"[?？]|\?$")
MARKER_RE = re.compile(r"\|\s*\*\*(?P<marker>[ㄱ-ㅎ①-⑤])\.?\*\*.*?\|\s*(?P<ox>[✅❌○×OX])[^|]*\|\s*(?P<basis>.*?)\s*\|")
BULLET_RE = re.compile(
    r"^\s*[-*]\s*\*\*(?P<marker>[ㄱ-ㅎ①-⑤])\.?\s*(?:[○×OX]|[✅❌])?.*?\*\*\s*[—-]\s*(?P<basis>.+)$"
)
HEADING_RE = re.compile(
    r"^\s*#{2,5}\s*(?P<marker>[ㄱ-ㅎ①-⑤])\s*(?:[○×OX✗✅❌])?\s*(?:[—-]\s*)?(?P<basis>.+)$"
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


MANUAL_REP_OVERRIDES_BY_ROUND = {
    12: {
        (10, "③"): "유치권 항변이 이유 있는 경우 법원은 피담보채권 지급과 목적물 인도를 동시에 이행하도록 명하는 판결을 하여야 한다.",
        (12, "ㄴ"): "특정유증 목적 부동산이 상속인의 무권리 처분으로 제3자 명의로 이전등기된 경우, 수증자는 제3자에게 직접 진정명의회복을 원인으로 한 이전등기를 청구할 수 없다.",
        (28, "④"): "주위토지통행권의 통행로는 통행을 위한 지역권처럼 항상 특정한 장소로 고정되는 것은 아니다.",
        (35, "③"): "계약 위반 제재와 이행 강제를 위하여 정한 위약벌에는 이자제한법상 최고이자율 제한 규정이 적용되지 않는다.",
        (52, "③"): "상사채권의 5년 소멸시효는 기본적 상행위뿐 아니라 상인이 영업을 위하여 한 보조적 상행위로 인한 채권에도 적용된다.",
        (56, "ㄱ"): "채권자취소소송의 수익자는 취소채권자에 대한 별개의 집행권원으로 취소채권자의 가액배상채권을 압류하고 전부명령을 받을 수 있다.",
        (56, "ㄴ"): "사해행위 전에 채권이 성립되어 있었다면 그 액수나 범위가 구체적으로 확정되지 않았더라도 채권자취소권의 피보전채권이 될 수 있다.",
        (56, "ㄷ"): "채권자취소권의 범위를 정할 때 채권액에는 사해행위 이후 사실심 변론종결시까지 발생한 이자나 지연손해금이 포함된다.",
        (56, "ㄹ"): "채권자가 충분한 물적 담보로 채무 전액에 대한 우선변제권을 확보하고 있으면 연대보증인의 유일재산 처분은 채권자에 대하여 사해행위가 성립하지 않는다.",
        (62, "③"): "문서에 찍힌 인영이 명의인의 인장에 의하여 현출된 것으로 인정되면 특별한 사정이 없는 한 그 문서 전체의 진정성립이 추정된다.",
        (66, "④"): "예비적 공동소송에서 화해권고결정에 대하여 일부 공동소송인이 이의하지 않으면 원칙적으로 그 공동소송인에 대한 관계에서는 결정이 분리확정될 수 있다.",
        (68, "②"): "소송목적인 권리를 양도받은 권리승계인이라도 상고심에서는 승계참가신청을 할 수 없다.",
    },
    13: {
        (2, "①"): "대부업자의 영업상 대여금 원금채권에는 상법 제64조의 5년 상사소멸시효가 적용된다.",
        (2, "②"): "1년 이내 기간으로 정한 변제기 전 약정이자채권에는 민법 제163조의 3년 단기소멸시효가 적용된다.",
        (2, "③"): "변제기 이후의 지연손해금채권은 원본채권의 변형물로서 원본채권의 소멸시효기간을 따른다.",
        (2, "④"): "원본채권이 소멸시효 완성으로 소멸하면 그 부수채권인 약정이자와 지연손해금도 함께 소멸한다.",
        (2, "⑤"): "소멸시효가 완성된 대여금과 시효가 완성되지 않은 대여금을 구별하여 원금, 약정이자, 지연손해금을 각각 산정하여야 한다.",
        (7, "①"): "법률행위의 효력 발생이나 소멸을 장래 불확실한 사실에 의존시키려는 의사가 있더라도 외부에 표시되지 않으면 조건이 되지 않는다.",
        (14, "⑤"): "부동산 명의수탁자가 수탁 부동산에 근저당권을 설정하였더라도, 그 사정만으로 매도인에게 피담보채무액 상당의 부당이득반환의무를 부담하지 않는다.",
        (17, "ㄹ"): "계약을 합의해제하면서 반환금에 붙일 이자를 별도로 약정하지 않은 경우, 법정해제의 원상회복 이자 규정이 당연히 적용되지는 않는다.",
        (20, "①"): "근저당권자가 경매를 신청하면 그 경매신청 시점에 피담보채권이 확정되므로, 그 뒤 발생한 추가 대여금은 그 근저당권의 우선변제 범위에 포함되지 않는다.",
        (20, "②"): "일부 대위변제가 있는 경우 원채권자는 잔존채권에 관하여 우선 변제받고, 일부 대위변제자는 그 뒤 남은 매각대금에서 대위변제 비율에 따라 변제받는다.",
        (20, "③"): "연대보증인들이 일부 대위변제를 한 경우, 보증인들 사이의 배당은 각자가 대위변제한 금액의 비율에 따라 정해진다.",
        (20, "④"): "근저당 실행 배당에서는 경매신청 당시 확정된 잔존채권을 먼저 변제한 뒤, 남은 금액을 일부 대위변제자들에게 대위변제 비율로 배분한다.",
        (20, "⑤"): "근저당권의 피담보채권 확정 후 발생한 추가 대여금은 근저당권의 우선변제 대상이 아니므로 매각대금에서 먼저 배당받을 수 없다.",
        (27, "ㄴ"): "사해행위취소판결 중 원상회복으로서의 가액배상 부분에는 가집행선고를 붙일 수 없다.",
        (33, "ㄱ"): "공동저당 목적물 중 채무자 소유 부동산이 먼저 경매되어 채권자가 전액 변제받은 경우, 그 부동산의 후순위저당권자는 물상보증인 소유 부동산에 대하여 채권자를 대위할 수 없다.",
        (34, "ㄱ"): "숙박업자가 투숙객과 체결하는 숙박계약은 객실의 일시 사용을 목적으로 하는 임대차계약의 성질을 가진다.",
        (38, "ㄱ"): "공동근저당권에서는 각 담보목적물이 공동으로 동일한 피담보채권을 담보하므로, 일부 목적물 경매 시 다른 담보목적물의 부담 부분을 고려하여 배당액을 산정한다.",
        (38, "ㄴ"): "피담보채권을 누적적으로 담보하는 근저당권에서는 각 담보목적물이 별도로 피담보채권을 담보하므로, 해당 목적물의 매각대금에서 채권최고액 범위 내 전액 배당받을 수 있다.",
        (38, "ㄷ"): "누적적 근저당권에서 선순위권자가 해당 목적물의 매각대금으로 전액 배당받으면, 후순위권자는 남은 매각대금 한도에서만 배당받는다.",
        (40, "ㄱ"): "타인의 사망을 보험사고로 하는 보험계약에서 피보험자의 서면동의를 요구하는 상법 규정은 강행법규이다.",
        (42, "ㄱ"): "이사의 직무수행에 대한 보상으로 지급되는 특별성과급은 상법상 이사의 보수에 포함된다.",
        (43, "⑤"): "유한책임회사는 자기 지분의 전부 또는 일부를 양수할 수 없고, 자기 지분을 취득하면 그 지분은 취득한 때에 소멸한다.",
        (45, "②"): "비상장회사에서 발행주식총수의 1퍼센트 이상을 보유한 주주는 다른 주주와 보유주식을 합산하여 회사에 이사의 책임추궁 소 제기를 청구할 수 있다.",
        (47, "ㄱ"): "지배주주는 회사의 경영상 목적 달성을 위하여 필요한 경우 미리 주주총회의 승인을 받아 소수주주에게 그 보유 주식의 매도를 청구할 수 있다.",
        (53, "①"): "피고의 주소지 법원은 보통재판적에 따른 일반관할 법원으로서 특별한 사정이 없는 한 청구 전부에 관하여 관할권을 가진다.",
        (53, "⑤"): "관할권 없는 법원에 소가 제기되었더라도 피고가 관할위반을 주장하지 않고 본안에 관하여 변론하면 그 법원에 변론관할이 생긴다.",
        (60, "③"): "손해배상책임을 공평의 원칙에 따라 제한할 필요가 있는 경우, 채무자의 상계항변은 책임제한을 한 뒤의 손해배상액을 기준으로 판단한다.",
    },
    14: {
        (11, "ㄷ"): (
            "사해행위취소와 원상회복으로 등기가 회복된 뒤 채무자가 다시 부동산을 제3자에게 양도한 경우, "
            "사해행위 이후에 채무자에 대한 채권을 취득한 채권자는 그 제3자 명의 등기의 말소를 청구할 수 없다."
        ),
        (14, "ㄴ"): (
            "유치권자가 유치물을 점유하기 위하여 건물에 거주하는 경우, 그 거주로 인한 토지 사용은 "
            "건물 점유에 따른 것이므로 토지 소유자에게 별도의 차임 상당 부당이득반환의무를 부담하지 않는다."
        ),
        (20, "④"): (
            "가등기 유용 합의가 가압류등기 등 이해관계인의 권리를 침해하는 경우, "
            "가등기 유용 합의의 당사자는 가압류권자에게 그 가등기의 유효를 주장할 수 없다."
        ),
        (23, "ㄱ"): (
            "공동저당 목적 부동산 중 일부만 사해행위로 이전된 경우, 가액배상액은 이전된 부동산 가액에서 "
            "그 부동산이 가액비율에 따라 부담하는 피담보채권액을 공제하여 산정한다."
        ),
        (23, "ㄴ"): (
            "공동저당 목적 부동산 전부가 일괄로 사해행위 이전된 경우, 가액배상액은 이전된 부동산 전체 가액에서 "
            "공동저당 피담보채권액을 공제하여 산정한다."
        ),
        (23, "ㄷ"): (
            "공동저당 목적물 중 채무자 소유 부동산과 물상보증인 소유 부동산이 섞여 있는 경우, "
            "채무자 소유 부동산이 그 피담보채권을 먼저 부담하는 것으로 보아 가액배상액을 산정한다."
        ),
        (29, "ㄱ"): (
            "면책적 채무인수인은 특별한 사정이 없는 한 본래 채무자에게 구상권을 행사할 수 없다."
        ),
        (29, "ㄹ"): (
            "여러 물상보증인 중 한 사람이 변제한 뒤 다른 물상보증인 소유 부동산의 제3취득자에게 "
            "채권자를 대위하려면 대위의 부기등기가 필요하다."
        ),
        (33, "ㄱ"): (
            "한정승인 후 상속인이 상속재산에 고유채권자 앞으로 근저당권을 설정한 경우, "
            "그 부동산의 경매절차에서 상속채권자가 그 근저당권자보다 당연히 선순위로 배당받는 것은 아니다."
        ),
        (34, "ㄴ"): (
            "상속개시 후 인지로 공동상속인이 된 자는 이미 처분된 상속재산 자체를 되찾을 수 없고, "
            "인지판결 확정일부터 3년 내에 다른 공동상속인에게 상속분 상당 가액의 지급을 청구할 수 있다."
        ),
        (35, "ㄷ"): (
            "상속회복청구권은 상속권 침해행위가 있은 날부터 10년이 지나면 소멸하므로, "
            "그 기간이 지난 뒤 후행 양수인에게도 상속회복청구를 할 수 없다."
        ),
        (41, "③"): (
            "채권자대위소송의 확정판결 후 채무자로부터 목적물을 양수한 사람이라도, "
            "전소 소송물과 후소 청구가 다르면 변론종결 후 승계인으로서 전소 기판력을 받지 않을 수 있다."
        ),
        (64, "ㄴ"): (
            "대주주와 투자자 사이의 약정에는 주주평등 원칙이 직접 적용되지는 않지만, "
            "회사와 투자자 사이의 약정과 결합되어 유효성이 판단될 수 있다."
        ),
    },
    15: MANUAL_REP_OVERRIDES,
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
        if line.startswith("|"):
            match = MARKER_RE.search(line)
        else:
            match = BULLET_RE.search(line) or HEADING_RE.search(line)
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
    source = json.loads((ASSETS / SOURCE_ASSET_NAME).read_text(encoding="utf-8"))
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
        manual_rep = MANUAL_REP_OVERRIDES_BY_ROUND.get(ROUND_NO, {}).get((q_no, marker))
        if manual_rep:
            principle = manual_rep
            flags = []
            info_tags.append("manual_override")
        pid = f"civil-bar{ROUND_NO}-q{q_no:02d}-{marker}"
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
        "title": f"제{ROUND_NO}회 변호사시험 민사법 최소 원리 atom 초안",
        "round": ROUND_NO,
        "year": source.get("year") or (2011 + ROUND_NO),
        "source": f"assets/{SOURCE_ASSET_NAME} + lex-bank explanation basis transformed into principle candidates",
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
    lines.append(f"# 제{payload['round']}회 민사법 최소 원리 atom 초안 검증")
    lines.append("")
    lines.append(f"- 기준: `assets/{SOURCE_ASSET_NAME}` + lex-bank 해설의 각 지문 검토")
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
    global ROUND_NO, SOURCE_ASSET_NAME, OUTPUT_ASSET_NAME, REPORT_PREFIX

    parser = argparse.ArgumentParser()
    parser.add_argument("--round", type=int, default=ROUND_NO)
    parser.add_argument("--source", default=None)
    parser.add_argument("--output", default=None)
    args = parser.parse_args()

    ROUND_NO = args.round
    SOURCE_ASSET_NAME = args.source or f"ox_civil_bar{ROUND_NO}.json"
    OUTPUT_ASSET_NAME = args.output or f"ox_civil_bar{ROUND_NO}_minimal_atoms_draft.json"
    REPORT_PREFIX = f"civil_bar{ROUND_NO}_minimal_atom_audit"

    payload, audit = build_candidates()
    write_json(ASSETS / OUTPUT_ASSET_NAME, payload)
    REPORTS.mkdir(exist_ok=True)
    write_json(REPORTS / f"{REPORT_PREFIX}.json", audit)
    (REPORTS / f"{REPORT_PREFIX}.md").write_text(
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
