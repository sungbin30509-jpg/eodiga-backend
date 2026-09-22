from pathlib import Path
import json

import pandas as pd


# ============================================================
# FLOW:MATE
# Departure Candidate Service
#
# 역할
# ------------------------------------------------------------
# Synthetic 사용자의
#
# planned_departure_time
# adjustable_minutes
#
# 를 이용해서
# 사용자별 5분 단위 출발시간 후보를 생성한다.
#
# 예)
# planned_departure_time = 18:30
# adjustable_minutes = 30
#
# →
#
# 18:00
# 18:05
# ...
# 18:30
# ...
# 18:55
# 19:00
#
# ============================================================


# ============================================================
# 1. 프로젝트 경로
# ============================================================

ROOT = Path(__file__).resolve().parents[2]


INPUT_FILE = (
    ROOT
    / "data"
    / "generated"
    / "synthetic_users_10000.csv"
)


OUTPUT_FILE = (
    ROOT
    / "data"
    / "generated"
    / "user_departure_candidates.csv"
)


SUMMARY_FILE = (
    ROOT
    / "data"
    / "generated"
    / "user_departure_candidates_summary.json"
)


# ============================================================
# 2. 설정
# ============================================================

TIME_STEP_MINUTES = 5


# ============================================================
# 3. HH:MM → 분
# ============================================================

def time_to_minutes(
    time_text,
):

    text = str(
        time_text
    ).strip()


    parts = (
        text.split(":")
    )


    if len(parts) != 2:

        raise ValueError(
            f"잘못된 시간 형식: {time_text}"
        )


    hour = int(
        parts[0]
    )


    minute = int(
        parts[1]
    )


    if not (
        0 <= hour <= 23
        and
        0 <= minute <= 59
    ):

        raise ValueError(
            f"잘못된 시간 값: {time_text}"
        )


    return (
        hour * 60
        +
        minute
    )


# ============================================================
# 4. 분 → HH:MM
#
# 24시간을 넘어가는 경우에도 방어적으로 처리
# ============================================================

def minutes_to_time(
    total_minutes,
):

    total_minutes = (
        int(
            total_minutes
        )
        %
        (24 * 60)
    )


    hour = (
        total_minutes
        //
        60
    )


    minute = (
        total_minutes
        %
        60
    )


    return (
        f"{hour:02d}:{minute:02d}"
    )


# ============================================================
# 5. 한 사용자 후보 생성
# ============================================================

def generate_candidates_for_user(
    row,
):

    user_id = str(
        row["user_id"]
    )


    planned_time = str(
        row["planned_departure_time"]
    ).strip()


    adjustable_minutes = int(
        row["adjustable_minutes"]
    )


    if adjustable_minutes < 0:

        raise ValueError(
            f"{user_id}: adjustable_minutes가 음수입니다."
        )


    planned_minutes = (
        time_to_minutes(
            planned_time
        )
    )


    start_minutes = (
        planned_minutes
        -
        adjustable_minutes
    )


    end_minutes = (
        planned_minutes
        +
        adjustable_minutes
    )


    candidate_rows = []


    candidate_index = 0


    for candidate_minutes in range(

        start_minutes,

        end_minutes + 1,

        TIME_STEP_MINUTES,

    ):

        offset_minutes = (

            candidate_minutes

            -

            planned_minutes

        )


        candidate_rows.append({

            "user_id":
                user_id,

            "origin_location_id":
                str(
                    row[
                        "origin_location_id"
                    ]
                ),

            "destination_location_id":
                str(
                    row[
                        "destination_location_id"
                    ]
                ),

            "planned_departure_time":
                planned_time,

            "adjustable_minutes":
                adjustable_minutes,

            "candidate_index":
                candidate_index,

            "candidate_departure_time":
                minutes_to_time(
                    candidate_minutes
                ),

            "offset_minutes":
                offset_minutes,

            "is_original_time":
                (
                    offset_minutes
                    ==
                    0
                ),

        })


        candidate_index += 1


    return candidate_rows


# ============================================================
# 6. 전체 생성
# ============================================================

def build_departure_candidates():

    print()

    print(
        "========================================"
    )

    print(
        "FLOW:MATE Departure Candidate Service"
    )

    print(
        "========================================"
    )


    # --------------------------------------------------------
    # 입력 파일 확인
    # --------------------------------------------------------

    if not INPUT_FILE.exists():

        raise FileNotFoundError(

            "Synthetic 사용자 파일을 찾을 수 없습니다.\n"
            f"{INPUT_FILE}"

        )


    users = pd.read_csv(
        INPUT_FILE,
        dtype={
            "user_id": str,
            "origin_location_id": str,
            "destination_location_id": str,
        },
    )


    required_columns = {

        "user_id",
        "origin_location_id",
        "destination_location_id",
        "planned_departure_time",
        "adjustable_minutes",

    }


    missing_columns = (

        required_columns

        -

        set(
            users.columns
        )

    )


    if missing_columns:

        raise ValueError(

            "필수 컬럼이 없습니다: "
            f"{sorted(missing_columns)}"

        )


    # --------------------------------------------------------
    # 중복 사용자 검사
    # --------------------------------------------------------

    duplicated_users = (

        users[
            "user_id"
        ]

        .duplicated()

        .sum()

    )


    if duplicated_users > 0:

        raise ValueError(

            f"user_id 중복이 {duplicated_users}개 있습니다."

        )


    print(
        "Synthetic 사용자:",
        f"{len(users):,}",
    )


    print(
        "시간 간격:",
        f"{TIME_STEP_MINUTES}분",
    )


    # ========================================================
    # 후보 생성
    # ========================================================

    all_candidates = []


    for _, row in users.iterrows():

        candidates = (
            generate_candidates_for_user(
                row
            )
        )


        all_candidates.extend(
            candidates
        )


    result = pd.DataFrame(
        all_candidates
    )


    # ========================================================
    # 검증
    # ========================================================

    original_count = int(

        result[
            "is_original_time"
        ]

        .sum()

    )


    candidate_counts = (

        result

        .groupby(
            "user_id"
        )

        .size()

    )


    min_candidate_count = int(
        candidate_counts.min()
    )


    max_candidate_count = int(
        candidate_counts.max()
    )


    average_candidate_count = float(
        candidate_counts.mean()
    )


    # --------------------------------------------------------
    # 모든 사용자에게 원래 시간이 정확히 1개 있는지 확인
    # --------------------------------------------------------

    original_per_user = (

        result[
            result[
                "is_original_time"
            ]
        ]

        .groupby(
            "user_id"
        )

        .size()

    )


    invalid_original_users = (

        original_per_user[
            original_per_user
            !=
            1
        ]

    )


    if len(
        original_per_user
    ) != len(
        users
    ):

        raise RuntimeError(

            "일부 사용자에게 원래 출발시간 후보가 없습니다."

        )


    if not invalid_original_users.empty:

        raise RuntimeError(

            "일부 사용자에게 원래 출발시간 후보가 "
            "2개 이상 생성되었습니다."

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


    # ========================================================
    # adjustable_minutes별 통계
    # ========================================================

    adjustable_distribution = (

        users[
            "adjustable_minutes"
        ]

        .value_counts()

        .sort_index()

        .to_dict()

    )


    adjustable_distribution = {

        str(
            int(key)
        ):
        int(
            value
        )

        for key, value
        in adjustable_distribution.items()

    }


    # ========================================================
    # Summary
    # ========================================================

    summary = {

        "user_count":
            int(
                len(
                    users
                )
            ),

        "candidate_row_count":
            int(
                len(
                    result
                )
            ),

        "time_step_minutes":
            TIME_STEP_MINUTES,

        "original_time_candidate_count":
            original_count,

        "min_candidates_per_user":
            min_candidate_count,

        "max_candidates_per_user":
            max_candidate_count,

        "average_candidates_per_user":
            round(
                average_candidate_count,
                2,
            ),

        "adjustable_minutes_distribution":
            adjustable_distribution,

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

    print(
        "========================================"
    )

    print(
        "생성 결과"
    )

    print(
        "========================================"
    )


    print(
        "사용자:",
        f"{len(users):,}",
    )


    print(
        "출발시간 후보:",
        f"{len(result):,}",
    )


    print(
        "원래 시간 후보:",
        f"{original_count:,}",
    )


    print(
        "사용자당 최소 후보:",
        min_candidate_count,
    )


    print(
        "사용자당 최대 후보:",
        max_candidate_count,
    )


    print(
        "사용자당 평균 후보:",
        round(
            average_candidate_count,
            2,
        ),
    )


    print()

    print(
        "adjustable_minutes 분포:"
    )


    for (
        adjustable,
        count,
    ) in adjustable_distribution.items():

        print(
            f"  ±{adjustable}분:",
            f"{count:,}명",
        )


    print()

    print(
        "결과:"
    )

    print(
        OUTPUT_FILE
    )


    print()

    print(
        "Summary:"
    )

    print(
        SUMMARY_FILE
    )


    print()

    print(
        "========================================"
    )

    print(
        "Departure Candidate 생성 완료"
    )

    print(
        "========================================"
    )


    return result


# ============================================================
# 7. 직접 실행
# ============================================================

if __name__ == "__main__":

    build_departure_candidates()