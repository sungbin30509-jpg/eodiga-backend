from pathlib import Path
import json

import pandas as pd


# ============================================================
# FLOW:MATE
# Departure Candidate ↔ OD Join Service
#
# 역할
# ------------------------------------------------------------
# user_departure_candidates.csv
#        +
# user_od_mapping.csv
#        ↓
# 각 출발시간 후보에 od_id를 연결한다.
#
# 이후:
# user × departure_time × OD × Route A/B/C
# 평가의 기반 데이터가 된다.
# ============================================================


ROOT = Path(__file__).resolve().parents[2]


CANDIDATE_FILE = (
    ROOT
    / "data"
    / "generated"
    / "user_departure_candidates.csv"
)


OD_MAPPING_FILE = (
    ROOT
    / "data"
    / "generated"
    / "user_od_mapping.csv"
)


OUTPUT_FILE = (
    ROOT
    / "data"
    / "generated"
    / "user_departure_candidates_with_od.csv"
)


SUMMARY_FILE = (
    ROOT
    / "data"
    / "generated"
    / "user_departure_candidates_with_od_summary.json"
)


def build_candidates_with_od():

    print()
    print("========================================")
    print("FLOW:MATE Departure Candidate + OD")
    print("========================================")


    # ========================================================
    # 파일 확인
    # ========================================================

    if not CANDIDATE_FILE.exists():

        raise FileNotFoundError(
            "출발시간 후보 파일을 찾을 수 없습니다.\n"
            f"{CANDIDATE_FILE}"
        )


    if not OD_MAPPING_FILE.exists():

        raise FileNotFoundError(
            "user_od_mapping.csv를 찾을 수 없습니다.\n"
            f"{OD_MAPPING_FILE}"
        )


    # ========================================================
    # 읽기
    # ========================================================

    candidates = pd.read_csv(
        CANDIDATE_FILE,
        dtype={
            "user_id": str,
            "origin_location_id": str,
            "destination_location_id": str,
        },
    )


    od_mapping = pd.read_csv(
        OD_MAPPING_FILE,
        dtype={
            "user_id": str,
            "od_id": str,
        },
    )


    print(
        "출발시간 후보:",
        f"{len(candidates):,}",
    )


    print(
        "OD Mapping 사용자:",
        f"{len(od_mapping):,}",
    )


    # ========================================================
    # 필수 컬럼 확인
    # ========================================================

    candidate_required = {
        "user_id",
        "candidate_departure_time",
        "planned_departure_time",
        "offset_minutes",
    }


    mapping_required = {
        "user_id",
        "od_id",
    }


    missing_candidate = (
        candidate_required
        -
        set(candidates.columns)
    )


    missing_mapping = (
        mapping_required
        -
        set(od_mapping.columns)
    )


    if missing_candidate:

        raise ValueError(
            "출발시간 후보 파일 필수 컬럼 누락: "
            f"{sorted(missing_candidate)}"
        )


    if missing_mapping:

        raise ValueError(
            "OD Mapping 파일 필수 컬럼 누락: "
            f"{sorted(missing_mapping)}"
        )


    # ========================================================
    # OD Mapping 중복 검사
    #
    # 한 user_id는 반드시 하나의 od_id만 가져야 한다.
    # ========================================================

    duplicate_users = (

        od_mapping[
            "user_id"
        ]

        .duplicated()

        .sum()

    )


    if duplicate_users > 0:

        raise ValueError(
            f"user_od_mapping에 중복 user_id가 "
            f"{duplicate_users}개 있습니다."
        )


    # 필요한 컬럼만 사용
    mapping_small = (

        od_mapping[
            [
                "user_id",
                "od_id",
            ]
        ]

        .copy()

    )


    # ========================================================
    # Join
    # ========================================================

    result = (

        candidates

        .merge(
            mapping_small,
            on="user_id",
            how="left",
            validate="many_to_one",
        )

    )


    # ========================================================
    # 검증
    # ========================================================

    if len(result) != len(candidates):

        raise RuntimeError(
            "Join 전후 행 수가 달라졌습니다."
        )


    missing_od_count = int(

        result[
            "od_id"
        ]

        .isna()

        .sum()

    )


    if missing_od_count > 0:

        missing_users = (

            result.loc[
                result[
                    "od_id"
                ].isna(),
                "user_id",
            ]

            .drop_duplicates()

            .tolist()

        )


        raise RuntimeError(
            "OD가 연결되지 않은 출발시간 후보가 있습니다.\n"
            f"행 수: {missing_od_count}\n"
            f"사용자 예시: {missing_users[:10]}"
        )


    # ========================================================
    # 컬럼 순서 정리
    # ========================================================

    preferred_columns = [

        "user_id",

        "od_id",

        "origin_location_id",

        "destination_location_id",

        "planned_departure_time",

        "adjustable_minutes",

        "candidate_index",

        "candidate_departure_time",

        "offset_minutes",

        "is_original_time",

    ]


    existing_preferred = [

        column

        for column
        in preferred_columns

        if column
        in result.columns

    ]


    remaining_columns = [

        column

        for column
        in result.columns

        if column
        not in existing_preferred

    ]


    result = result[

        existing_preferred
        +
        remaining_columns

    ]


    # ========================================================
    # 통계
    # ========================================================

    unique_users = int(
        result[
            "user_id"
        ].nunique()
    )


    unique_ods = int(
        result[
            "od_id"
        ].nunique()
    )


    original_count = int(

        result[
            "is_original_time"
        ]

        .sum()

    )


    # ========================================================
    # 저장
    # ========================================================

    OUTPUT_FILE.parent.mkdir(
        parents=True,
        exist_ok=True,
    )


    result.to_csv(
        OUTPUT_FILE,
        index=False,
        encoding="utf-8-sig",
    )


    summary = {

        "row_count":
            int(
                len(result)
            ),

        "unique_user_count":
            unique_users,

        "unique_od_count":
            unique_ods,

        "missing_od_count":
            missing_od_count,

        "original_time_candidate_count":
            original_count,

        "output_file":
            str(
                OUTPUT_FILE
            ),

    }


    with open(
        SUMMARY_FILE,
        "w",
        encoding="utf-8",
    ) as file:

        json.dump(
            summary,
            file,
            ensure_ascii=False,
            indent=2,
        )


    # ========================================================
    # 출력
    # ========================================================

    print()
    print("========================================")
    print("Join 결과")
    print("========================================")


    print(
        "전체 후보:",
        f"{len(result):,}",
    )


    print(
        "Unique 사용자:",
        f"{unique_users:,}",
    )


    print(
        "Unique OD:",
        f"{unique_ods:,}",
    )


    print(
        "OD 누락:",
        missing_od_count,
    )


    print(
        "원래 출발시간 후보:",
        f"{original_count:,}",
    )


    print()
    print("결과:")
    print(OUTPUT_FILE)


    print()
    print("Summary:")
    print(SUMMARY_FILE)


    print()
    print("========================================")
    print("Departure Candidate + OD 연결 완료")
    print("========================================")


    return result


if __name__ == "__main__":

    build_candidates_with_od()