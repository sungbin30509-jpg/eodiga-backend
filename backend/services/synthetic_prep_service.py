from pathlib import Path
import argparse
import json
import time

import pandas as pd

from backend.services.location_service import (
    resolve_location,
)


# ============================================================
# FLOW:MATE
# Synthetic Commuter Preparation Service
#
# 역할
# ------------------------------------------------------------
# 가상 직장인 CSV
#        ↓
# 장소 중복 제거
#        ↓
# TMAP Location Resolver
#        ↓
# 실제 좌표 부착
#        ↓
# Unique OD 추출
#
#
# 중요
# ------------------------------------------------------------
# 10,000명을 한 명씩 TMAP 검색하지 않는다.
#
# 동일 location_id는 한 번만 검색하고
# 결과를 모든 사용자에게 재사용한다.
# ============================================================


# ============================================================
# 1. 프로젝트 경로
# ============================================================

ROOT = (
    Path(__file__)
    .resolve()
    .parents[2]
)


DEFAULT_INPUT_FILE = (
    ROOT
    / "data"
    / "synthetic"
    / "commuters.csv"
)


OUTPUT_DIR = (
    ROOT
    / "data"
    / "synthetic"
    / "processed"
)


OUTPUT_DIR.mkdir(
    parents=True,
    exist_ok=True,
)


# ============================================================
# 2. 출력 파일
# ============================================================

RESOLVED_LOCATIONS_FILE = (
    OUTPUT_DIR
    / "resolved_locations.csv"
)


UNRESOLVED_LOCATIONS_FILE = (
    OUTPUT_DIR
    / "unresolved_locations.csv"
)


RESOLVED_COMMUTERS_FILE = (
    OUTPUT_DIR
    / "resolved_commuters.csv"
)


UNIQUE_ODS_FILE = (
    OUTPUT_DIR
    / "unique_ods.csv"
)


SUMMARY_FILE = (
    OUTPUT_DIR
    / "synthetic_prep_summary.json"
)


# ============================================================
# 3. 필수 컬럼
# ============================================================

REQUIRED_COLUMNS = [

    "user_id",

    "origin_location_id",

    "origin_name",

    "origin_type",

    "destination_location_id",

    "destination_name",

    "destination_type",

    "destination_region",

    "planned_departure_time",

    "adjustable_minutes",

]


# ============================================================
# 4. 문자열 정리
# ============================================================

def clean_text(
    value,
):

    if value is None:

        return ""


    if pd.isna(
        value
    ):

        return ""


    return (
        str(value)
        .strip()
    )


# ============================================================
# 5. CSV 읽기
# ============================================================

def read_commuters(
    input_file,
):

    input_file = Path(
        input_file
    )


    if not input_file.exists():

        raise FileNotFoundError(

            "가상 직장인 CSV를 찾을 수 없습니다.\n"
            f"{input_file}"

        )


    # ========================================================
    # UTF-8 우선
    # 실패 시 CP949
    # ========================================================

    try:

        df = pd.read_csv(
            input_file,
            dtype=str,
            encoding="utf-8-sig",
        )


    except UnicodeDecodeError:

        df = pd.read_csv(
            input_file,
            dtype=str,
            encoding="cp949",
        )


    if df.empty:

        raise ValueError(
            "가상 직장인 CSV가 비어 있습니다."
        )


    # ========================================================
    # 컬럼명 공백 제거
    # ========================================================

    df.columns = [

        str(column)
        .strip()

        for column
        in df.columns

    ]


    # ========================================================
    # 필수 컬럼 확인
    # ========================================================

    missing_columns = [

        column

        for column
        in REQUIRED_COLUMNS

        if column
        not in df.columns

    ]


    if missing_columns:

        raise ValueError(

            "필수 컬럼이 없습니다.\n"
            f"{missing_columns}\n\n"
            f"현재 컬럼:\n{df.columns.tolist()}"

        )


    # ========================================================
    # 주요 문자열 정리
    # ========================================================

    for column in REQUIRED_COLUMNS:

        df[column] = (

            df[column]
            .apply(
                clean_text
            )

        )


    return df


# ============================================================
# 6. 장소 목록 생성
#
# origin / destination을 하나의 Location Table로 합친다.
# ============================================================

def build_unique_locations(
    commuters,
):

    # ========================================================
    # 출발지
    # ========================================================

    origins = pd.DataFrame({

        "location_id":
        commuters[
            "origin_location_id"
        ],

        "name":
        commuters[
            "origin_name"
        ],

        "location_type":
        commuters[
            "origin_type"
        ],

        # 프로젝트상 출발지는 판교 등
        # 성남 업무지역 중심
        "region_hint":
        "성남시",

        "source_role":
        "origin",

    })


    # ========================================================
    # 도착지
    # ========================================================

    destinations = pd.DataFrame({

        "location_id":
        commuters[
            "destination_location_id"
        ],

        "name":
        commuters[
            "destination_name"
        ],

        "location_type":
        commuters[
            "destination_type"
        ],

        "region_hint":
        commuters[
            "destination_region"
        ],

        "source_role":
        "destination",

    })


    locations = pd.concat(
        [
            origins,
            destinations,
        ],
        ignore_index=True,
    )


    # ========================================================
    # 빈 장소 제거
    # ========================================================

    locations[
        "location_id"
    ] = (

        locations[
            "location_id"
        ]
        .apply(
            clean_text
        )

    )


    locations[
        "name"
    ] = (

        locations[
            "name"
        ]
        .apply(
            clean_text
        )

    )


    locations[
        "region_hint"
    ] = (

        locations[
            "region_hint"
        ]
        .apply(
            clean_text
        )

    )


    locations = locations[

        (
            locations[
                "location_id"
            ]
            !=
            ""
        )

        &

        (
            locations[
                "name"
            ]
            !=
            ""
        )

    ].copy()


    # ========================================================
    # 핵심:
    #
    # location_id 기준 중복 제거
    #
    # 같은 장소를 100명이 사용해도
    # TMAP 조회는 1번
    # ========================================================

    locations = (

        locations

        .drop_duplicates(

            subset=[
                "location_id"
            ],

            keep="first",

        )

        .reset_index(
            drop=True
        )

    )


    return locations


# ============================================================
# 7. 장소 1개 Resolve
# ============================================================

def resolve_single_location(
    row,
):

    location_id = clean_text(
        row[
            "location_id"
        ]
    )


    name = clean_text(
        row[
            "name"
        ]
    )


    region_hint = clean_text(
        row[
            "region_hint"
        ]
    )


    if not region_hint:

        region_hint = None


    try:

        resolved = (
            resolve_location(

                name,

                region_hint=(
                    region_hint
                ),

            )
        )


        return {

            "status":
            "resolved",

            "location_id":
            location_id,

            "input_name":
            name,

            "location_type":
            clean_text(
                row[
                    "location_type"
                ]
            ),

            "region_hint":
            region_hint
            or
            "",

            "source_role":
            clean_text(
                row[
                    "source_role"
                ]
            ),

            "resolved_name":
            resolved.get(
                "name",
                "",
            ),

            "resolved_address":
            resolved.get(
                "address",
                "",
            ),

            "lat":
            resolved.get(
                "lat"
            ),

            "lon":
            resolved.get(
                "lon"
            ),

            "poi_id":
            resolved.get(
                "poi_id"
            ),

            "match_score":
            resolved.get(
                "match_score"
            ),

            "location_source":
            resolved.get(
                "source"
            ),

            "cached":
            resolved.get(
                "cached",
                False,
            ),

            "error":
            "",

        }


    except Exception as error:

        return {

            "status":
            "failed",

            "location_id":
            location_id,

            "input_name":
            name,

            "location_type":
            clean_text(
                row[
                    "location_type"
                ]
            ),

            "region_hint":
            region_hint
            or
            "",

            "source_role":
            clean_text(
                row[
                    "source_role"
                ]
            ),

            "resolved_name":
            "",

            "resolved_address":
            "",

            "lat":
            None,

            "lon":
            None,

            "poi_id":
            None,

            "match_score":
            None,

            "location_source":
            None,

            "cached":
            False,

            "error":
            str(
                error
            ),

        }


# ============================================================
# 8. Unique Location 전체 Resolve
# ============================================================

def resolve_unique_locations(
    locations,
    sleep_sec=0.05,
):

    results = []


    total = len(
        locations
    )


    print()

    print(
        "========================================"
    )

    print(
        "Unique Location Resolve"
    )

    print(
        "========================================"
    )


    print(
        "중복 제거 후 장소:",
        total,
        "개",
    )


    for index, row in (
        locations.iterrows()
    ):

        number = (
            index
            +
            1
        )


        print(

            f"[{number}/{total}]",

            row[
                "name"
            ],

            "|",

            row[
                "region_hint"
            ],

            "...",

            end=" ",

            flush=True,

        )


        result = (
            resolve_single_location(
                row
            )
        )


        results.append(
            result
        )


        if (
            result[
                "status"
            ]
            ==
            "resolved"
        ):

            print(

                "✅",

                result[
                    "resolved_name"
                ],

                "| cached:",

                result[
                    "cached"
                ],

            )


        else:

            print(
                "❌",
                result[
                    "error"
                ],
            )


        # 과도한 연속 호출 방지
        if sleep_sec > 0:

            time.sleep(
                sleep_sec
            )


    return pd.DataFrame(
        results
    )


# ============================================================
# 9. 사용자 데이터에 좌표 붙이기
# ============================================================

def attach_resolved_locations(
    commuters,
    resolved_locations,
):

    # ========================================================
    # 성공한 장소만 사용
    # ========================================================

    resolved = resolved_locations[

        resolved_locations[
            "status"
        ]
        ==
        "resolved"

    ].copy()


    # ========================================================
    # Merge용 Location Table
    # ========================================================

    lookup = resolved[

        [
            "location_id",
            "resolved_name",
            "resolved_address",
            "lat",
            "lon",
            "poi_id",
        ]

    ].copy()


    # ========================================================
    # 출발지 Merge
    # ========================================================

    origin_lookup = (
        lookup.rename(
            columns={
                "location_id":
                "origin_location_id",

                "resolved_name":
                "origin_resolved_name",

                "resolved_address":
                "origin_address",

                "lat":
                "origin_lat",

                "lon":
                "origin_lon",

                "poi_id":
                "origin_poi_id",
            }
        )
    )


    result = commuters.merge(

        origin_lookup,

        on="origin_location_id",

        how="left",

    )


    # ========================================================
    # 도착지 Merge
    # ========================================================

    destination_lookup = (
        lookup.rename(
            columns={
                "location_id":
                "destination_location_id",

                "resolved_name":
                "destination_resolved_name",

                "resolved_address":
                "destination_address",

                "lat":
                "destination_lat",

                "lon":
                "destination_lon",

                "poi_id":
                "destination_poi_id",
            }
        )
    )


    result = result.merge(

        destination_lookup,

        on="destination_location_id",

        how="left",

    )


    # ========================================================
    # 사용자 Resolve 성공 여부
    # ========================================================

    result[
        "location_resolve_status"
    ] = (

        result.apply(

            lambda row:

            "resolved"

            if (

                pd.notna(
                    row[
                        "origin_lat"
                    ]
                )

                and

                pd.notna(
                    row[
                        "origin_lon"
                    ]
                )

                and

                pd.notna(
                    row[
                        "destination_lat"
                    ]
                )

                and

                pd.notna(
                    row[
                        "destination_lon"
                    ]
                )

            )

            else

            "failed",

            axis=1,

        )

    )


    return result


# ============================================================
# 10. Unique OD 생성
# ============================================================

def build_unique_ods(
    resolved_commuters,
):

    valid = resolved_commuters[

        resolved_commuters[
            "location_resolve_status"
        ]
        ==
        "resolved"

    ].copy()


    # ========================================================
    # OD Key
    #
    # origin_location_id
    # +
    # destination_location_id
    # ========================================================

    valid[
        "od_key"
    ] = (

        valid[
            "origin_location_id"
        ]

        +

        "__to__"

        +

        valid[
            "destination_location_id"
        ]

    )


    # ========================================================
    # 각 OD를 사용하는 사용자 수
    # ========================================================

    usage = (

        valid

        .groupby(
            "od_key"
        )

        .size()

        .reset_index(
            name="user_count"
        )

    )


    # ========================================================
    # OD 대표 정보
    # ========================================================

    unique_ods = (

        valid

        .drop_duplicates(

            subset=[
                "od_key"
            ],

            keep="first",

        )

        [

            [
                "od_key",

                "origin_location_id",

                "origin_name",

                "origin_resolved_name",

                "origin_address",

                "origin_lat",

                "origin_lon",

                "destination_location_id",

                "destination_name",

                "destination_resolved_name",

                "destination_address",

                "destination_lat",

                "destination_lon",

            ]

        ]

    )


    unique_ods = unique_ods.merge(

        usage,

        on="od_key",

        how="left",

    )


    # ========================================================
    # 많이 사용되는 OD 우선
    # ========================================================

    unique_ods = (

        unique_ods

        .sort_values(

            by="user_count",

            ascending=False,

        )

        .reset_index(
            drop=True
        )

    )


    unique_ods[
        "od_rank"
    ] = (

        unique_ods.index

        +

        1

    )


    return unique_ods


# ============================================================
# 11. 전체 실행
# ============================================================

def prepare_synthetic_commuters(
    input_file=DEFAULT_INPUT_FILE,
):

    input_file = Path(
        input_file
    )


    print()

    print(
        "========================================"
    )

    print(
        "FLOW:MATE Synthetic Preparation"
    )

    print(
        "========================================"
    )


    print()

    print(
        "입력:"
    )


    print(
        input_file
    )


    # ========================================================
    # STEP 1
    # CSV
    # ========================================================

    print()

    print(
        "[1/5] 가상 직장인 CSV 읽기"
    )


    commuters = (
        read_commuters(
            input_file
        )
    )


    print(
        "사용자:",
        f"{len(commuters):,}",
        "명",
    )


    # ========================================================
    # STEP 2
    # Unique Location
    # ========================================================

    print()

    print(
        "[2/5] 중복 장소 제거"
    )


    unique_locations = (
        build_unique_locations(
            commuters
        )
    )


    print(
        "Unique Location:",
        f"{len(unique_locations):,}",
        "개",
    )


    # ========================================================
    # STEP 3
    # Location Resolver
    # ========================================================

    print()

    print(
        "[3/5] TMAP Location Resolve"
    )


    resolved_locations = (
        resolve_unique_locations(
            unique_locations
        )
    )


    successful_locations = resolved_locations[

        resolved_locations[
            "status"
        ]
        ==
        "resolved"

    ].copy()


    failed_locations = resolved_locations[

        resolved_locations[
            "status"
        ]
        ==
        "failed"

    ].copy()


    # ========================================================
    # 저장
    # ========================================================

    successful_locations.to_csv(

        RESOLVED_LOCATIONS_FILE,

        index=False,

        encoding="utf-8-sig",

    )


    failed_locations.to_csv(

        UNRESOLVED_LOCATIONS_FILE,

        index=False,

        encoding="utf-8-sig",

    )


    # ========================================================
    # STEP 4
    # 사용자 데이터에 좌표 붙이기
    # ========================================================

    print()

    print(
        "[4/5] 사용자 데이터에 실제 좌표 연결"
    )


    resolved_commuters = (
        attach_resolved_locations(

            commuters,

            resolved_locations,

        )
    )


    resolved_commuters.to_csv(

        RESOLVED_COMMUTERS_FILE,

        index=False,

        encoding="utf-8-sig",

    )


    resolved_user_count = int(

        (
            resolved_commuters[
                "location_resolve_status"
            ]
            ==
            "resolved"
        )
        .sum()

    )


    failed_user_count = (

        len(
            resolved_commuters
        )

        -

        resolved_user_count

    )


    # ========================================================
    # STEP 5
    # Unique OD
    # ========================================================

    print()

    print(
        "[5/5] Unique OD 생성"
    )


    unique_ods = (
        build_unique_ods(
            resolved_commuters
        )
    )


    unique_ods.to_csv(

        UNIQUE_ODS_FILE,

        index=False,

        encoding="utf-8-sig",

    )


    # ========================================================
    # Summary
    # ========================================================

    summary = {

        "input_file":
        str(
            input_file
        ),

        "total_users":
        len(
            commuters
        ),

        "unique_location_count":
        len(
            unique_locations
        ),

        "resolved_location_count":
        len(
            successful_locations
        ),

        "unresolved_location_count":
        len(
            failed_locations
        ),

        "resolved_user_count":
        resolved_user_count,

        "failed_user_count":
        failed_user_count,

        "unique_od_count":
        len(
            unique_ods
        ),

        "output_files":
        {

            "resolved_locations":
            str(
                RESOLVED_LOCATIONS_FILE
            ),

            "unresolved_locations":
            str(
                UNRESOLVED_LOCATIONS_FILE
            ),

            "resolved_commuters":
            str(
                RESOLVED_COMMUTERS_FILE
            ),

            "unique_ods":
            str(
                UNIQUE_ODS_FILE
            ),

        },

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
        "Synthetic Preparation 결과"
    )

    print(
        "========================================"
    )


    print(
        "전체 사용자:",
        f"{len(commuters):,}",
    )


    print(
        "Unique Location:",
        f"{len(unique_locations):,}",
    )


    print(
        "Resolve 성공 장소:",
        f"{len(successful_locations):,}",
    )


    print(
        "Resolve 실패 장소:",
        f"{len(failed_locations):,}",
    )


    print(
        "좌표 연결 성공 사용자:",
        f"{resolved_user_count:,}",
    )


    print(
        "좌표 연결 실패 사용자:",
        f"{failed_user_count:,}",
    )


    print(
        "Unique OD:",
        f"{len(unique_ods):,}",
    )


    print()

    print(
        "저장:"
    )


    print(
        RESOLVED_LOCATIONS_FILE
    )


    print(
        UNRESOLVED_LOCATIONS_FILE
    )


    print(
        RESOLVED_COMMUTERS_FILE
    )


    print(
        UNIQUE_ODS_FILE
    )


    print(
        SUMMARY_FILE
    )


    print()

    print(
        "========================================"
    )

    print(
        "Synthetic Preparation 완료"
    )

    print(
        "========================================"
    )


    return {

        "commuters":
        resolved_commuters,

        "locations":
        resolved_locations,

        "unique_ods":
        unique_ods,

        "summary":
        summary,

    }


# ============================================================
# 12. CLI
# ============================================================

def main():

    parser = argparse.ArgumentParser(

        description=(
            "FLOW:MATE Synthetic Commuter Preparation"
        )

    )


    parser.add_argument(

        "--input",

        default=str(
            DEFAULT_INPUT_FILE
        ),

        help=(
            "Synthetic commuter CSV 경로"
        ),

    )


    args = (
        parser.parse_args()
    )


    prepare_synthetic_commuters(
        args.input
    )


if __name__ == "__main__":

    main()