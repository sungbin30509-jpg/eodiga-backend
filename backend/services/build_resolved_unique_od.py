from pathlib import Path
import json

import pandas as pd


# ============================================================
# FLOW:MATE
# Resolved Unique OD Builder
#
# unique_od_summary.csv
# +
# resolved_location_master.csv
#        ↓
# 출발지 / 목적지 실제 좌표 연결
#        ↓
# resolved_unique_od.csv
# ============================================================


# ============================================================
# 1. 프로젝트 경로
# ============================================================

ROOT = (
    Path(__file__)
    .resolve()
    .parents[2]
)


LOCATION_FILE = (
    ROOT
    / "data"
    / "master"
    / "resolved_location_master.csv"
)


OD_FILE = (
    ROOT
    / "data"
    / "generated"
    / "unique_od_summary.csv"
)


OUTPUT_FILE = (
    ROOT
    / "data"
    / "generated"
    / "resolved_unique_od.csv"
)


SUMMARY_FILE = (
    ROOT
    / "data"
    / "generated"
    / "resolved_unique_od_summary.json"
)


# ============================================================
# 2. 문자열 정리
# ============================================================

def clean_text(value):

    if value is None:
        return ""

    if pd.isna(value):
        return ""

    return str(value).strip()


# ============================================================
# 3. Location Master 읽기
# ============================================================

def load_locations():

    if not LOCATION_FILE.exists():

        raise FileNotFoundError(
            "resolved_location_master.csv를 찾을 수 없습니다.\n"
            f"{LOCATION_FILE}"
        )


    df = pd.read_csv(
        LOCATION_FILE,
        dtype={
            "location_id": str,
            "poi_id": str,
        },
        encoding="utf-8-sig",
    )


    required_columns = [
        "location_id",
        "input_name",
        "resolved_name",
        "resolved_address",
        "lat",
        "lon",
        "poi_id",
    ]


    missing = [
        column
        for column in required_columns
        if column not in df.columns
    ]


    if missing:

        raise ValueError(
            "resolved_location_master.csv "
            "필수 컬럼 누락:\n"
            f"{missing}"
        )


    df["location_id"] = (
        df["location_id"]
        .apply(clean_text)
    )


    # ========================================================
    # 중복 Location 검사
    # ========================================================

    duplicated = (
        df["location_id"]
        .duplicated(
            keep=False
        )
    )


    if duplicated.any():

        duplicate_ids = (
            df.loc[
                duplicated,
                "location_id"
            ]
            .tolist()
        )


        raise ValueError(
            "resolved_location_master.csv에 "
            "중복 location_id가 있습니다.\n"
            f"{duplicate_ids}"
        )


    # ========================================================
    # 좌표 숫자 변환
    # ========================================================

    df["lat"] = pd.to_numeric(
        df["lat"],
        errors="coerce",
    )


    df["lon"] = pd.to_numeric(
        df["lon"],
        errors="coerce",
    )


    invalid_coordinates = df[
        df["lat"].isna()
        |
        df["lon"].isna()
    ]


    if not invalid_coordinates.empty:

        raise ValueError(
            "좌표가 없는 Location이 있습니다.\n"
            f"{invalid_coordinates['location_id'].tolist()}"
        )


    return df


# ============================================================
# 4. Unique OD 읽기
# ============================================================

def load_unique_od():

    if not OD_FILE.exists():

        raise FileNotFoundError(
            "unique_od_summary.csv를 찾을 수 없습니다.\n"
            f"{OD_FILE}"
        )


    df = pd.read_csv(
        OD_FILE,
        dtype=str,
        encoding="utf-8-sig",
    )


    required_columns = [
        "od_id",
        "origin_location_id",
        "origin_name",
        "destination_location_id",
        "destination_name",
        "destination_region",
        "user_count",
    ]


    missing = [
        column
        for column in required_columns
        if column not in df.columns
    ]


    if missing:

        raise ValueError(
            "unique_od_summary.csv "
            "필수 컬럼 누락:\n"
            f"{missing}"
        )


    for column in [
        "od_id",
        "origin_location_id",
        "destination_location_id",
    ]:

        df[column] = (
            df[column]
            .apply(clean_text)
        )


    df["user_count"] = pd.to_numeric(
        df["user_count"],
        errors="raise",
    ).astype(int)


    # ========================================================
    # OD ID 중복 검사
    # ========================================================

    if df["od_id"].duplicated().any():

        duplicate_ids = (
            df.loc[
                df["od_id"].duplicated(
                    keep=False
                ),
                "od_id"
            ]
            .tolist()
        )


        raise ValueError(
            "중복 od_id가 있습니다.\n"
            f"{duplicate_ids}"
        )


    # ========================================================
    # Origin + Destination 조합 중복 검사
    # ========================================================

    duplicated_od = df.duplicated(

        subset=[
            "origin_location_id",
            "destination_location_id",
        ],

        keep=False,

    )


    if duplicated_od.any():

        duplicate_rows = df.loc[
            duplicated_od,
            [
                "origin_location_id",
                "destination_location_id",
            ],
        ]


        raise ValueError(
            "중복 OD 조합이 있습니다.\n"
            f"{duplicate_rows.to_dict('records')}"
        )


    return df


# ============================================================
# 5. Location Lookup
# ============================================================

def build_location_lookup(
    locations,
):

    lookup = {}


    for _, row in locations.iterrows():

        location_id = clean_text(
            row["location_id"]
        )


        lookup[location_id] = {

            "resolved_name":
                clean_text(
                    row["resolved_name"]
                ),

            "resolved_address":
                clean_text(
                    row["resolved_address"]
                ),

            "lat":
                float(
                    row["lat"]
                ),

            "lon":
                float(
                    row["lon"]
                ),

            "poi_id":
                clean_text(
                    row["poi_id"]
                ),

        }


    return lookup


# ============================================================
# 6. OD 하나에 좌표 연결
# ============================================================

def resolve_od_row(
    row,
    location_lookup,
):

    origin_id = clean_text(
        row["origin_location_id"]
    )


    destination_id = clean_text(
        row["destination_location_id"]
    )


    # ========================================================
    # Location 존재 검사
    # ========================================================

    if origin_id not in location_lookup:

        raise ValueError(
            f"{row['od_id']}: "
            f"출발지 {origin_id}가 "
            "resolved_location_master.csv에 없습니다."
        )


    if destination_id not in location_lookup:

        raise ValueError(
            f"{row['od_id']}: "
            f"목적지 {destination_id}가 "
            "resolved_location_master.csv에 없습니다."
        )


    origin = location_lookup[
        origin_id
    ]


    destination = location_lookup[
        destination_id
    ]


    return {

        "od_id":
            clean_text(
                row["od_id"]
            ),

        # ----------------------------------------------------
        # 출발지
        # ----------------------------------------------------

        "origin_location_id":
            origin_id,

        "origin_name":
            clean_text(
                row["origin_name"]
            ),

        "origin_resolved_name":
            origin[
                "resolved_name"
            ],

        "origin_address":
            origin[
                "resolved_address"
            ],

        "origin_lat":
            origin[
                "lat"
            ],

        "origin_lon":
            origin[
                "lon"
            ],

        "origin_poi_id":
            origin[
                "poi_id"
            ],

        # ----------------------------------------------------
        # 목적지
        # ----------------------------------------------------

        "destination_location_id":
            destination_id,

        "destination_name":
            clean_text(
                row["destination_name"]
            ),

        "destination_resolved_name":
            destination[
                "resolved_name"
            ],

        "destination_address":
            destination[
                "resolved_address"
            ],

        "destination_lat":
            destination[
                "lat"
            ],

        "destination_lon":
            destination[
                "lon"
            ],

        "destination_poi_id":
            destination[
                "poi_id"
            ],

        "destination_region":
            clean_text(
                row["destination_region"]
            ),

        # ----------------------------------------------------
        # 이 OD를 사용하는 Synthetic 사용자 수
        # ----------------------------------------------------

        "user_count":
            int(
                row["user_count"]
            ),

    }


# ============================================================
# 7. 전체 OD 연결
# ============================================================

def build_resolved_unique_od():

    print()

    print(
        "========================================"
    )

    print(
        "FLOW:MATE Resolved Unique OD Builder"
    )

    print(
        "========================================"
    )


    # ========================================================
    # STEP 1
    # Location
    # ========================================================

    print()

    print(
        "[1/4] Resolved Location Master 읽기"
    )


    locations = (
        load_locations()
    )


    print(
        "Location 수:",
        len(locations),
    )


    # ========================================================
    # STEP 2
    # OD
    # ========================================================

    print()

    print(
        "[2/4] Unique OD 읽기"
    )


    unique_od = (
        load_unique_od()
    )


    print(
        "Unique OD 수:",
        len(unique_od),
    )


    print(
        "Synthetic 사용자 합계:",
        f"{unique_od['user_count'].sum():,}",
    )


    # ========================================================
    # STEP 3
    # Lookup + JOIN
    # ========================================================

    print()

    print(
        "[3/4] OD에 실제 좌표 연결"
    )


    location_lookup = (
        build_location_lookup(
            locations
        )
    )


    resolved_rows = []


    total = len(
        unique_od
    )


    for index, row in (
        unique_od.iterrows()
    ):

        resolved_rows.append(

            resolve_od_row(

                row,

                location_lookup,

            )

        )


        current = (
            index
            +
            1
        )


        if (
            current % 100 == 0
            or
            current == total
        ):

            print(
                f"{current}/{total} 완료"
            )


    resolved_df = pd.DataFrame(
        resolved_rows
    )


    # ========================================================
    # STEP 4
    # 최종 검증
    # ========================================================

    print()

    print(
        "[4/4] 최종 검증"
    )


    # --------------------------------------------------------
    # OD 개수
    # --------------------------------------------------------

    if (
        len(resolved_df)
        !=
        len(unique_od)
    ):

        raise ValueError(
            "OD 수가 달라졌습니다."
        )


    # --------------------------------------------------------
    # 좌표 누락
    # --------------------------------------------------------

    coordinate_columns = [

        "origin_lat",
        "origin_lon",

        "destination_lat",
        "destination_lon",

    ]


    if (

        resolved_df[
            coordinate_columns
        ]

        .isna()

        .any()

        .any()

    ):

        raise ValueError(
            "좌표가 누락된 OD가 있습니다."
        )


    # --------------------------------------------------------
    # user_count 합계
    # --------------------------------------------------------

    total_users = int(
        resolved_df[
            "user_count"
        ]
        .sum()
    )


    if total_users != 10000:

        raise ValueError(

            "OD user_count 합계가 "
            "10,000명이 아닙니다.\n"
            f"현재: {total_users:,}"

        )


    # ========================================================
    # 저장
    # ========================================================

    OUTPUT_FILE.parent.mkdir(
        parents=True,
        exist_ok=True,
    )


    resolved_df.to_csv(

        OUTPUT_FILE,

        index=False,

        encoding="utf-8-sig",

    )


    # ========================================================
    # Summary
    # ========================================================

    summary = {

        "location_count":
            len(
                locations
            ),

        "unique_od_count":
            len(
                resolved_df
            ),

        "synthetic_user_count":
            total_users,

        "origin_location_count":
            resolved_df[
                "origin_location_id"
            ]
            .nunique(),

        "destination_location_count":
            resolved_df[
                "destination_location_id"
            ]
            .nunique(),

        "missing_coordinate_count":
            int(

                resolved_df[
                    coordinate_columns
                ]

                .isna()

                .any(
                    axis=1
                )

                .sum()

            ),

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
    # 결과 출력
    # ========================================================

    print()

    print(
        "========================================"
    )

    print(
        "Resolved Unique OD 결과"
    )

    print(
        "========================================"
    )


    print(

        "Location:",

        len(
            locations
        ),

    )


    print(

        "출발지:",

        summary[
            "origin_location_count"
        ],

    )


    print(

        "목적지:",

        summary[
            "destination_location_count"
        ],

    )


    print(

        "Unique OD:",

        summary[
            "unique_od_count"
        ],

    )


    print(

        "Synthetic 사용자:",

        f"{total_users:,}",

    )


    print(

        "좌표 누락 OD:",

        summary[
            "missing_coordinate_count"
        ],

    )


    print()

    print(
        "저장:"
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
        "✅ Resolved Unique OD 생성 완료"
    )

    print(
        "========================================"
    )


    return resolved_df


# ============================================================
# 8. 직접 실행
# ============================================================

if __name__ == "__main__":

    build_resolved_unique_od()