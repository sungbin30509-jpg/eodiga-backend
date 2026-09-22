from pathlib import Path
import json

import geopandas as gpd


# ============================================================
# FLOW:MATE
# Seongnam LINK Universe v2 Builder
#
# 입력
# ------------------------------------------------------------
# data/
# ├── national_links/
# │   └── MOCT_LINK.shp
# │
# └── boundaries/
#     └── sigungu/
#         └── BND_SIGUNGU_PG.shp
#
#
# 출력
# ------------------------------------------------------------
# data/
# └── universe/
#     ├── seongnam_link_universe_v2.parquet
#     ├── seongnam_link_universe_v2.csv
#     ├── seongnam_boundary.geojson
#     └── seongnam_link_universe_summary.json
#
#
# 성남시 경계 정의
# ------------------------------------------------------------
# 성남시 수정구
# +
# 성남시 중원구
# +
# 성남시 분당구
#
# ============================================================


# ============================================================
# 1. 프로젝트 경로
# ============================================================

ROOT = Path(__file__).resolve().parent


NATIONAL_LINK_DIR = (
    ROOT
    / "data"
    / "national_links"
)


BOUNDARY_DIR = (
    ROOT
    / "data"
    / "boundaries"
    / "sigungu"
)


OUTPUT_DIR = (
    ROOT
    / "data"
    / "universe"
)


OUTPUT_DIR.mkdir(
    parents=True,
    exist_ok=True,
)


# ============================================================
# 2. 출력 파일
# ============================================================

OUTPUT_PARQUET = (
    OUTPUT_DIR
    / "seongnam_link_universe_v2.parquet"
)


OUTPUT_CSV = (
    OUTPUT_DIR
    / "seongnam_link_universe_v2.csv"
)


OUTPUT_BOUNDARY = (
    OUTPUT_DIR
    / "seongnam_boundary.geojson"
)


OUTPUT_SUMMARY = (
    OUTPUT_DIR
    / "seongnam_link_universe_summary.json"
)


# ============================================================
# 3. 성남시 행정구 이름
#
# 실제 BND_SIGUNGU_PG.shp 안의
# SIGUNGU_NM 값 기준
# ============================================================

SEONGNAM_DISTRICTS = [

    "성남시 수정구",

    "성남시 중원구",

    "성남시 분당구",

]


# ============================================================
# 4. SHP 파일 검색
# ============================================================

def find_shp_file(
    directory: Path,
    preferred_keyword=None,
):

    if not directory.exists():

        raise FileNotFoundError(
            f"폴더가 없습니다: {directory}"
        )


    shp_files = sorted(
        directory.rglob("*.shp")
    )


    if not shp_files:

        raise FileNotFoundError(
            f"SHP 파일을 찾을 수 없습니다: {directory}"
        )


    # --------------------------------------------------------
    # 원하는 파일명이 있으면 우선 사용
    # --------------------------------------------------------

    if preferred_keyword:

        matches = [

            path

            for path in shp_files

            if preferred_keyword.lower()
            in path.name.lower()

        ]


        if matches:

            return matches[0]


    # --------------------------------------------------------
    # SHP가 하나면 바로 사용
    # --------------------------------------------------------

    if len(shp_files) == 1:

        return shp_files[0]


    # --------------------------------------------------------
    # 여러 개라면 목록 표시
    # --------------------------------------------------------

    print()

    print(
        "발견된 SHP 파일:"
    )


    for index, path in enumerate(
        shp_files,
        start=1,
    ):

        print(
            f"{index}. {path}"
        )


    print()

    print(
        "첫 번째 SHP 파일을 사용합니다."
    )


    return shp_files[0]


# ============================================================
# 5. 성남시 3개 구 추출
# ============================================================

def find_seongnam_rows(
    boundary_gdf: gpd.GeoDataFrame,
):

    print()

    print(
        "======================================"
    )

    print(
        "행정경계 컬럼"
    )

    print(
        "======================================"
    )


    print(
        boundary_gdf.columns.tolist()
    )


    # --------------------------------------------------------
    # SIGUNGU_NM 컬럼 확인
    # --------------------------------------------------------

    if "SIGUNGU_NM" not in boundary_gdf.columns:

        raise ValueError(

            "행정경계 SHP에 "
            "SIGUNGU_NM 컬럼이 없습니다. "
            f"현재 컬럼: {boundary_gdf.columns.tolist()}"

        )


    # --------------------------------------------------------
    # 이름 정리
    # --------------------------------------------------------

    names = (

        boundary_gdf[
            "SIGUNGU_NM"
        ]

        .fillna("")

        .astype(str)

        .str.strip()

    )


    # --------------------------------------------------------
    # 성남시 수정구 / 중원구 / 분당구 추출
    # --------------------------------------------------------

    result = boundary_gdf[

        names.isin(
            SEONGNAM_DISTRICTS
        )

    ].copy()


    print()

    print(
        "성남시 구성 행정구:",
        SEONGNAM_DISTRICTS,
    )


    print(
        "찾은 경계 개수:",
        len(result),
    )


    # --------------------------------------------------------
    # 하나도 못 찾은 경우
    # --------------------------------------------------------

    if result.empty:

        print()

        print(
            "성남시 행정구역을 찾지 못했습니다."
        )


        print()

        print(
            "SIGUNGU_NM 샘플:"
        )


        print(

            boundary_gdf[
                "SIGUNGU_NM"
            ]

            .dropna()

            .astype(str)

            .head(150)

            .to_string(
                index=False
            )

        )


        raise ValueError(
            "성남시 행정경계를 찾지 못했습니다."
        )


    # --------------------------------------------------------
    # 찾은 성남 행정구 출력
    # --------------------------------------------------------

    display_columns = [

        column

        for column in [

            "BASE_DATE",

            "SIGUNGU_CD",

            "SIGUNGU_NM",

        ]

        if column
        in result.columns

    ]


    print()

    print(
        "찾은 성남시 행정구:"
    )


    print(

        result[
            display_columns
        ]

        .to_string(
            index=False
        )

    )


    # --------------------------------------------------------
    # 성남 3개 구가 모두 존재하는지 확인
    # --------------------------------------------------------

    found_names = set(

        result[
            "SIGUNGU_NM"
        ]

        .astype(str)

        .str.strip()

        .tolist()

    )


    expected_names = set(
        SEONGNAM_DISTRICTS
    )


    missing_names = (

        expected_names

        -

        found_names

    )


    if missing_names:

        raise ValueError(

            "성남시 행정구역 중 일부를 "
            "찾지 못했습니다: "
            f"{sorted(missing_names)}"

        )


    # --------------------------------------------------------
    # 정확히 3개인지 확인
    # --------------------------------------------------------

    if len(result) != 3:

        raise ValueError(

            "성남시 행정경계가 정확히 "
            "3개가 아닙니다. "
            f"현재 개수: {len(result)}"

        )


    print()

    print(
        "성남시 수정구 / 중원구 / 분당구 "
        "3개 경계 확인 완료"
    )


    return result


# ============================================================
# 6. 수정구 + 중원구 + 분당구
#    → 성남시 하나의 Polygon으로 결합
# ============================================================

def build_seongnam_boundary(
    boundary_gdf: gpd.GeoDataFrame,
):

    seongnam_rows = (
        find_seongnam_rows(
            boundary_gdf
        )
    )


    # --------------------------------------------------------
    # GeoPandas 버전 호환
    # --------------------------------------------------------

    try:

        merged_geometry = (

            seongnam_rows
            .geometry
            .union_all()

        )


    except AttributeError:

        merged_geometry = (

            seongnam_rows
            .geometry
            .unary_union

        )


    # --------------------------------------------------------
    # 하나의 성남시 GeoDataFrame 생성
    # --------------------------------------------------------

    seongnam = gpd.GeoDataFrame(

        [

            {

                "name": "성남시",

                "district_count": 3,

                "geometry": (
                    merged_geometry
                ),

            }

        ],

        crs=boundary_gdf.crs,

    )


    # --------------------------------------------------------
    # geometry 확인
    # --------------------------------------------------------

    if (

        seongnam
        .geometry
        .iloc[0]
        is None

        or

        seongnam
        .geometry
        .iloc[0]
        .is_empty

    ):

        raise ValueError(
            "성남시 경계를 합치는 데 실패했습니다."
        )


    return seongnam


# ============================================================
# 7. MOCT_LINK 기본 정리
# ============================================================

def prepare_links(
    links: gpd.GeoDataFrame,
):

    # --------------------------------------------------------
    # LINK_ID 존재 확인
    # --------------------------------------------------------

    if "LINK_ID" not in links.columns:

        raise ValueError(
            "MOCT_LINK에 LINK_ID 컬럼이 없습니다."
        )


    links = links.copy()


    # --------------------------------------------------------
    # LINK_ID는 반드시 문자열로 유지
    # --------------------------------------------------------

    links[
        "LINK_ID"
    ] = (

        links[
            "LINK_ID"
        ]

        .astype(str)

        .str.strip()

    )


    # --------------------------------------------------------
    # geometry 없는 LINK 제거
    # --------------------------------------------------------

    links = links[

        links.geometry.notna()

    ].copy()


    links = links[

        ~links.geometry.is_empty

    ].copy()


    return links


# ============================================================
# 8. 성남과 교차하는 후보 LINK 검색
# ============================================================

def spatial_candidate_links(
    links: gpd.GeoDataFrame,
    seongnam: gpd.GeoDataFrame,
):

    boundary_geometry = (

        seongnam
        .geometry
        .iloc[0]

    )


    # --------------------------------------------------------
    # Spatial Index 사용
    #
    # 전국 155만 LINK 전체에
    # intersection을 하지 않고
    # 먼저 후보만 추림
    # --------------------------------------------------------

    candidate_indexes = (

        links
        .sindex
        .query(

            boundary_geometry,

            predicate="intersects",

        )

    )


    candidates = (

        links
        .iloc[
            candidate_indexes
        ]
        .copy()

    )


    # --------------------------------------------------------
    # LINK_ID 중복 방지
    # --------------------------------------------------------

    candidates = (

        candidates
        .drop_duplicates(

            subset="LINK_ID",

            keep="first",

        )

        .copy()

    )


    return candidates


# ============================================================
# 9. LINK별 성남 내부 길이 계산
# ============================================================

def calculate_overlap(
    links: gpd.GeoDataFrame,
    seongnam: gpd.GeoDataFrame,
):

    boundary_geometry = (

        seongnam
        .geometry
        .iloc[0]

    )


    result = links.copy()


    # --------------------------------------------------------
    # LINK 전체 길이
    #
    # MOCT_LINK CRS가 meter 기반 투영좌표계이므로
    # geometry.length 사용
    # --------------------------------------------------------

    result[
        "geometry_length_m"
    ] = (

        result
        .geometry
        .length

    )


    # --------------------------------------------------------
    # 성남시 Polygon과 실제 교차하는 geometry
    # --------------------------------------------------------

    intersection_geometry = (

        result
        .geometry
        .intersection(
            boundary_geometry
        )

    )


    # --------------------------------------------------------
    # 성남 내부에 포함되는 길이
    # --------------------------------------------------------

    result[
        "seongnam_overlap_m"
    ] = (

        intersection_geometry
        .length

    )


    # --------------------------------------------------------
    # 비정상 0m LINK 제거
    # --------------------------------------------------------

    result = result[

        result[
            "geometry_length_m"
        ]
        > 0

    ].copy()


    # --------------------------------------------------------
    # 성남 내부 비율
    # --------------------------------------------------------

    result[
        "seongnam_overlap_ratio"
    ] = (

        result[
            "seongnam_overlap_m"
        ]

        /

        result[
            "geometry_length_m"
        ]

    )


    result[
        "seongnam_overlap_ratio"
    ] = (

        result[
            "seongnam_overlap_ratio"
        ]

        .fillna(0.0)

        .clip(
            lower=0.0,
            upper=1.0,
        )

    )


    # --------------------------------------------------------
    # 경계에 점처럼 살짝 닿는 LINK 제외
    #
    # 실제 성남 내부 길이가 1m보다 커야
    # Universe에 포함
    # --------------------------------------------------------

    result = result[

        result[
            "seongnam_overlap_m"
        ]
        > 1.0

    ].copy()


    # --------------------------------------------------------
    # 위치 상태 분류
    #
    # 99% 이상:
    #   inside
    #
    # 일부만 성남:
    #   boundary_crossing
    # --------------------------------------------------------

    def classify_position(
        ratio,
    ):

        if ratio >= 0.99:

            return "inside"


        return "boundary_crossing"


    result[
        "seongnam_position"
    ] = (

        result[
            "seongnam_overlap_ratio"
        ]

        .apply(
            classify_position
        )

    )


    # --------------------------------------------------------
    # 이 파일은 성남과 실제 길이 기준으로
    # 겹치는 LINK만 포함하므로 True
    # --------------------------------------------------------

    result[
        "inside_seongnam"
    ] = True


    return result


# ============================================================
# 10. 출력 컬럼 선택
# ============================================================

def select_output_columns(
    gdf: gpd.GeoDataFrame,
):

    desired_columns = [

        "LINK_ID",

        "F_NODE",

        "T_NODE",

        "ROAD_NAME",

        "ROAD_NO",

        "ROAD_RANK",

        "ROAD_TYPE",

        "LANES",

        "MAX_SPD",

        "LENGTH",

        "UPDATEDATE",

        "geometry_length_m",

        "seongnam_overlap_m",

        "seongnam_overlap_ratio",

        "seongnam_position",

        "inside_seongnam",

        "geometry",

    ]


    available_columns = [

        column

        for column
        in desired_columns

        if column
        in gdf.columns

    ]


    return gdf[
        available_columns
    ].copy()


# ============================================================
# 11. Summary 생성
# ============================================================

def make_summary(
    result: gpd.GeoDataFrame,
    link_file: Path,
    boundary_file: Path,
):

    road_counts = {}


    # --------------------------------------------------------
    # 도로명 TOP 50
    # --------------------------------------------------------

    if "ROAD_NAME" in result.columns:

        counts = (

            result[
                "ROAD_NAME"
            ]

            .fillna(
                "(도로명 없음)"
            )

            .astype(str)

            .value_counts()

            .head(50)

        )


        road_counts = {

            str(
                road_name
            ):
            int(
                count
            )

            for road_name, count
            in counts.items()

        }


    inside_count = int(

        (

            result[
                "seongnam_position"
            ]

            ==
            "inside"

        ).sum()

    )


    crossing_count = int(

        (

            result[
                "seongnam_position"
            ]

            ==
            "boundary_crossing"

        ).sum()

    )


    summary = {

        "project":
        "FLOW:MATE SEONGNAM",

        "universe_version":
        "v2",

        "node_link_source":
        link_file.name,

        "boundary_source":
        boundary_file.name,

        "boundary_definition":
        (
            "성남시 수정구 + "
            "성남시 중원구 + "
            "성남시 분당구"
        ),

        "working_crs":
        str(
            result.crs
        ),

        "total_seongnam_links":
        int(
            len(result)
        ),

        "fully_inside_links":
        inside_count,

        "boundary_crossing_links":
        crossing_count,

        "total_link_geometry_length_km":
        round(

            float(

                result[
                    "geometry_length_m"
                ].sum()

            )
            / 1000,

            3,

        ),

        "total_seongnam_overlap_km":
        round(

            float(

                result[
                    "seongnam_overlap_m"
                ].sum()

            )
            / 1000,

            3,

        ),

        "top_road_names":
        road_counts,

    }


    return summary


# ============================================================
# 12. 주요 도로 출력
# ============================================================

def print_top_roads(
    result: gpd.GeoDataFrame,
):

    if "ROAD_NAME" not in result.columns:

        return


    print()

    print(
        "========================================"
    )

    print(
        "성남 주요 도로 LINK 수 TOP 30"
    )

    print(
        "========================================"
    )


    road_counts = (

        result[
            "ROAD_NAME"
        ]

        .fillna(
            "(도로명 없음)"
        )

        .astype(str)

        .value_counts()

        .head(30)

    )


    print(
        road_counts.to_string()
    )


# ============================================================
# MAIN
# ============================================================

def main():

    print()

    print(
        "========================================"
    )

    print(
        "FLOW:MATE"
    )

    print(
        "Seongnam LINK Universe v2 Builder"
    )

    print(
        "========================================"
    )


    # ========================================================
    # SHP 파일 찾기
    # ========================================================

    link_file = find_shp_file(

        NATIONAL_LINK_DIR,

        preferred_keyword="MOCT_LINK",

    )


    boundary_file = find_shp_file(

        BOUNDARY_DIR,

        preferred_keyword="BND_SIGUNGU_PG",

    )


    print()

    print(
        "MOCT_LINK:",
        link_file,
    )


    print(
        "Boundary :",
        boundary_file,
    )


    # ========================================================
    # [1/7] MOCT_LINK 로드
    # ========================================================

    print()

    print(
        "[1/7] MOCT_LINK 읽는 중..."
    )


    links = gpd.read_file(
        link_file
    )


    print(
        "전체 LINK:",
        f"{len(links):,}",
    )


    print(
        "MOCT_LINK CRS:",
        links.crs,
    )


    links = prepare_links(
        links
    )


    # ========================================================
    # [2/7] 행정경계 로드
    # ========================================================

    print()

    print(
        "[2/7] 행정경계 읽는 중..."
    )


    boundaries = gpd.read_file(
        boundary_file
    )


    print(
        "경계 객체:",
        f"{len(boundaries):,}",
    )


    print(
        "Boundary CRS:",
        boundaries.crs,
    )


    # ========================================================
    # [3/7] 성남시 경계 생성
    # ========================================================

    print()

    print(
        "[3/7] 성남시 경계 추출..."
    )


    seongnam = (
        build_seongnam_boundary(
            boundaries
        )
    )


    # ========================================================
    # [4/7] CRS 통일
    # ========================================================

    print()

    print(
        "[4/7] CRS 통일..."
    )


    if links.crs is None:

        raise ValueError(
            "MOCT_LINK CRS 정보가 없습니다."
        )


    if seongnam.crs is None:

        raise ValueError(
            "행정경계 CRS 정보가 없습니다."
        )


    # --------------------------------------------------------
    # 행정경계 CRS
    # →
    # MOCT_LINK CRS
    # --------------------------------------------------------

    seongnam = (

        seongnam
        .to_crs(
            links.crs
        )

    )


    print(
        "작업 CRS:",
        links.crs,
    )


    # ========================================================
    # 성남시 경계 GeoJSON 저장
    #
    # 지도에서 사용하기 위해 EPSG:4326
    # ========================================================

    seongnam_wgs84 = (

        seongnam
        .to_crs(
            "EPSG:4326"
        )

    )


    seongnam_wgs84.to_file(

        OUTPUT_BOUNDARY,

        driver="GeoJSON",

    )


    print()

    print(
        "성남 경계 GeoJSON 저장:"
    )


    print(
        OUTPUT_BOUNDARY
    )


    # ========================================================
    # [5/7] 후보 LINK 추출
    # ========================================================

    print()

    print(
        "[5/7] 성남과 교차하는 LINK 검색..."
    )


    candidates = (

        spatial_candidate_links(

            links,

            seongnam,

        )

    )


    print(
        "공간 후보 LINK:",
        f"{len(candidates):,}",
    )


    # 전국 155만 LINK 메모리 해제
    del links


    # ========================================================
    # [6/7] 실제 overlap 계산
    # ========================================================

    print()

    print(
        "[6/7] 성남 내부 길이 계산..."
    )


    result = (

        calculate_overlap(

            candidates,

            seongnam,

        )

    )


    result = (

        select_output_columns(
            result
        )

    )


    result = (

        result

        .sort_values(
            "LINK_ID"
        )

        .reset_index(
            drop=True
        )

    )


    # ========================================================
    # 결과 통계
    # ========================================================

    inside_count = int(

        (

            result[
                "seongnam_position"
            ]

            ==
            "inside"

        ).sum()

    )


    crossing_count = int(

        (

            result[
                "seongnam_position"
            ]

            ==
            "boundary_crossing"

        ).sum()

    )


    print()

    print(
        "========================================"
    )

    print(
        "성남 LINK Universe 결과"
    )

    print(
        "========================================"
    )


    print(
        "총 LINK:",
        f"{len(result):,}",
    )


    print(
        "성남 완전 내부 LINK:",
        f"{inside_count:,}",
    )


    print(
        "성남 경계 교차 LINK:",
        f"{crossing_count:,}",
    )


    print(

        "성남 내부 총 길이:",

        (
            f"{result['seongnam_overlap_m'].sum() / 1000:.2f} km"
        ),

    )


    # ========================================================
    # [7/7] 저장
    # ========================================================

    print()

    print(
        "[7/7] 결과 저장..."
    )


    # --------------------------------------------------------
    # GeoParquet
    # geometry 포함
    # --------------------------------------------------------

    result.to_parquet(

        OUTPUT_PARQUET,

        index=False,

    )


    # --------------------------------------------------------
    # CSV
    # geometry 제외
    # --------------------------------------------------------

    csv_result = (

        result

        .drop(

            columns=[
                "geometry"
            ],

            errors="ignore",

        )

        .copy()

    )


    csv_result.to_csv(

        OUTPUT_CSV,

        index=False,

        encoding="utf-8-sig",

    )


    # --------------------------------------------------------
    # Summary JSON
    # --------------------------------------------------------

    summary = make_summary(

        result,

        link_file,

        boundary_file,

    )


    with open(

        OUTPUT_SUMMARY,

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
    # 저장 완료 출력
    # ========================================================

    print()

    print(
        "========================================"
    )

    print(
        "저장 완료"
    )

    print(
        "========================================"
    )


    print()

    print(
        "Parquet:"
    )

    print(
        OUTPUT_PARQUET
    )


    print()

    print(
        "CSV:"
    )

    print(
        OUTPUT_CSV
    )


    print()

    print(
        "Boundary GeoJSON:"
    )

    print(
        OUTPUT_BOUNDARY
    )


    print()

    print(
        "Summary:"
    )

    print(
        OUTPUT_SUMMARY
    )


    # ========================================================
    # 주요 도로 출력
    # ========================================================

    print_top_roads(
        result
    )


    # ========================================================
    # LINK 샘플 출력
    # ========================================================

    print()

    print(
        "========================================"
    )

    print(
        "LINK 샘플"
    )

    print(
        "========================================"
    )


    sample_columns = [

        column

        for column in [

            "LINK_ID",

            "ROAD_NAME",

            "F_NODE",

            "T_NODE",

            "geometry_length_m",

            "seongnam_overlap_m",

            "seongnam_overlap_ratio",

            "seongnam_position",

        ]

        if column
        in result.columns

    ]


    print(

        result[
            sample_columns
        ]

        .head(20)

        .to_string(
            index=False
        )

    )


    print()

    print(
        "========================================"
    )

    print(
        "성남 LINK Universe v2 생성 완료"
    )

    print(
        "========================================"
    )


# ============================================================
# 실행
# ============================================================

if __name__ == "__main__":

    main()