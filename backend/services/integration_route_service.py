from pathlib import Path
import json
import math

import pandas as pd


# ============================================================
# 언제가 / FLOW:MATE
# Real Route Integration Service
#
# 역할
# ------------------------------------------------------------
# export_route_integration_dataset.py가 만든
#
# 1. success_od_manifest.csv
# 2. route_catalog.csv
# 3. route_links.csv
# 4. route_integration_summary.json
#
# 을 읽어서 FastAPI에서 사용할 수 있는 형태로 제공한다.
#
# 추가 기능
# ------------------------------------------------------------
# 원본 OD JSON에서 실제 TMAP Polyline Geometry도 조회한다.
#
# 중요
# ------------------------------------------------------------
# - TMAP API 신규 호출 없음
# - LightGBM 신규 호출 없음
# - 기존에 저장된 실제 Route / LINK 데이터만 사용
# ============================================================


# ============================================================
# 프로젝트 경로
# ============================================================

ROOT = Path(__file__).resolve().parents[2]


INTEGRATION_DIR = (
    ROOT
    / "data"
    / "integration"
)


OD_PIPELINE_DIR = (
    ROOT
    / "data"
    / "routes"
    / "od_pipeline"
)


SUCCESS_OD_FILE = (
    INTEGRATION_DIR
    / "success_od_manifest.csv"
)


ROUTE_CATALOG_FILE = (
    INTEGRATION_DIR
    / "route_catalog.csv"
)


ROUTE_LINKS_FILE = (
    INTEGRATION_DIR
    / "route_links.csv"
)


SUMMARY_FILE = (
    INTEGRATION_DIR
    / "route_integration_summary.json"
)


# ============================================================
# 메모리 Cache
#
# FastAPI 요청마다 54,000행 이상의 CSV를 다시 읽지 않도록
# 메모리에 저장한다.
#
# CSV가 다시 생성되면 파일 수정시간/크기를 비교해서
# 자동 Reload 한다.
# ============================================================

_cache = {

    "signature": None,

    "success_od": None,

    "routes": None,

    "links": None,

    "summary": None,

}


# ============================================================
# 필수 파일 확인
# ============================================================

def _check_files():

    required_files = [

        SUCCESS_OD_FILE,

        ROUTE_CATALOG_FILE,

        ROUTE_LINKS_FILE,

        SUMMARY_FILE,

    ]


    missing_files = [

        str(path)

        for path in required_files

        if not path.exists()

    ]


    if missing_files:

        raise FileNotFoundError(

            "Integration Dataset 파일이 없습니다.\n\n"

            + "\n".join(
                missing_files
            )

            + "\n\n"

            + "먼저 아래 명령을 실행하세요.\n"

            + "python -m "
              "backend.services."
              "export_route_integration_dataset"

        )


# ============================================================
# 파일 Signature 생성
#
# 파일이 변경되었는지 감지하기 위해
#
# - 수정시간
# - 파일크기
#
# 를 사용한다.
# ============================================================

def _build_signature():

    _check_files()


    paths = [

        SUCCESS_OD_FILE,

        ROUTE_CATALOG_FILE,

        ROUTE_LINKS_FILE,

        SUMMARY_FILE,

    ]


    return tuple(

        (

            str(path),

            path.stat().st_mtime_ns,

            path.stat().st_size,

        )

        for path in paths

    )


# ============================================================
# JSON 안전 변환
#
# pandas / numpy 값,
# NaN,
# Infinity 등이 FastAPI JSON 반환에서
# 문제되지 않도록 Python 기본 타입으로 변환한다.
# ============================================================

def _json_safe(
    value,
):

    # --------------------------------------------------------
    # Dict
    # --------------------------------------------------------

    if isinstance(
        value,
        dict,
    ):

        return {

            str(key):
                _json_safe(
                    item
                )

            for key, item
            in value.items()

        }


    # --------------------------------------------------------
    # List
    # --------------------------------------------------------

    if isinstance(
        value,
        list,
    ):

        return [

            _json_safe(
                item
            )

            for item
            in value

        ]


    # --------------------------------------------------------
    # Tuple
    # --------------------------------------------------------

    if isinstance(
        value,
        tuple,
    ):

        return [

            _json_safe(
                item
            )

            for item
            in value

        ]


    # --------------------------------------------------------
    # pandas / numpy NaN
    # --------------------------------------------------------

    try:

        if pd.isna(
            value
        ):

            return None

    except Exception:

        pass


    # --------------------------------------------------------
    # numpy scalar
    # --------------------------------------------------------

    if hasattr(
        value,
        "item",
    ):

        try:

            return value.item()

        except Exception:

            pass


    # --------------------------------------------------------
    # Infinity 방어
    # --------------------------------------------------------

    if isinstance(
        value,
        float,
    ):

        if not math.isfinite(
            value
        ):

            return None


    return value


# ============================================================
# DataFrame → JSON Records
# ============================================================

def _records(
    dataframe,
):

    records = dataframe.to_dict(
        orient="records"
    )


    return _json_safe(
        records
    )


# ============================================================
# CSV / Summary Loader
# ============================================================

def _load_data():

    signature = (
        _build_signature()
    )


    # --------------------------------------------------------
    # 파일이 변경되지 않았으면 기존 Cache 재사용
    # --------------------------------------------------------

    if (

        _cache[
            "signature"
        ]
        ==
        signature

        and

        _cache[
            "success_od"
        ]
        is not None

    ):

        return


    # ========================================================
    # Success OD
    # ========================================================

    success_od = pd.read_csv(

        SUCCESS_OD_FILE,

        dtype={

            "od_id":
                str,

            "origin_location_id":
                str,

            "destination_location_id":
                str,

        },

    )


    # ========================================================
    # Route Catalog
    # ========================================================

    routes = pd.read_csv(

        ROUTE_CATALOG_FILE,

        dtype={

            "route_id":
                str,

            "od_id":
                str,

            "candidate_id":
                str,

            "search_option":
                str,

        },

    )


    # ========================================================
    # Route LINK
    # ========================================================

    links = pd.read_csv(

        ROUTE_LINKS_FILE,

        dtype={

            "route_id":
                str,

            "od_id":
                str,

            "candidate_id":
                str,

            "link_id":
                str,

            "f_node":
                str,

            "t_node":
                str,

        },

    )


    # ========================================================
    # Summary
    # ========================================================

    with open(

        SUMMARY_FILE,

        "r",

        encoding="utf-8",

    ) as file:

        summary = json.load(
            file
        )


    # ========================================================
    # 문자열 정리
    # ========================================================

    for column in [

        "od_id",

    ]:

        if column in success_od.columns:

            success_od[
                column
            ] = (

                success_od[
                    column
                ]

                .astype(
                    str
                )

                .str.strip()

            )


    for column in [

        "route_id",

        "od_id",

        "candidate_id",

    ]:

        if column in routes.columns:

            routes[
                column
            ] = (

                routes[
                    column
                ]

                .astype(
                    str
                )

                .str.strip()

            )


    for column in [

        "route_id",

        "od_id",

        "candidate_id",

        "link_id",

    ]:

        if column in links.columns:

            links[
                column
            ] = (

                links[
                    column
                ]

                .astype(
                    str
                )

                .str.strip()

            )


    # ========================================================
    # Cache 저장
    # ========================================================

    _cache[
        "signature"
    ] = signature


    _cache[
        "success_od"
    ] = success_od


    _cache[
        "routes"
    ] = routes


    _cache[
        "links"
    ] = links


    _cache[
        "summary"
    ] = summary


# ============================================================
# Boolean Series 변환
#
# CSV에서 True/False가 문자열 또는 bool로 들어오는 경우를
# 모두 처리한다.
# ============================================================

def _true_mask(
    series,
):

    return (

        series

        .astype(
            str
        )

        .str.strip()

        .str.lower()

        .isin(
            [
                "true",
                "1",
                "yes",
            ]
        )

    )


# ============================================================
# Integration 전체 상태
#
# 반환 예:
#
# success_od_count
# route_candidate_count
# mapped_route_count
# usable_route_count
# route_link_row_count
# unique_link_count
# traffic_source_distribution
# ============================================================

def get_integration_status():

    _load_data()


    success_od = (
        _cache[
            "success_od"
        ]
    )


    routes = (
        _cache[
            "routes"
        ]
    )


    links = (
        _cache[
            "links"
        ]
    )


    summary = (
        _cache[
            "summary"
        ]
    )


    # ========================================================
    # Usable Route
    # ========================================================

    usable_routes = routes


    if (
        "is_usable"
        in
        routes.columns
    ):

        usable_routes = routes[

            _true_mask(

                routes[
                    "is_usable"
                ]

            )

        ]


    # ========================================================
    # Mapped Route
    # ========================================================

    mapped_routes = routes


    if (
        "mapping_status"
        in
        routes.columns
    ):

        mapped_routes = routes[

            routes[
                "mapping_status"
            ]

            .astype(
                str
            )

            .str.strip()

            .str.lower()

            ==
            "mapped"

        ]


    # ========================================================
    # Unique LINK
    # ========================================================

    unique_links = 0


    if (

        not links.empty

        and

        "link_id"
        in
        links.columns

    ):

        unique_links = int(

            links[
                "link_id"
            ].nunique()

        )


    # ========================================================
    # Traffic Source
    # ========================================================

    traffic_source = {}


    if (

        not links.empty

        and

        "traffic_source"
        in
        links.columns

    ):

        traffic_source = {

            str(key):
                int(value)

            for key, value

            in (

                links[
                    "traffic_source"
                ]

                .fillna(
                    "unknown"
                )

                .value_counts()

                .to_dict()

                .items()

            )

        }


    # ========================================================
    # Response
    # ========================================================

    return _json_safe({

        "status":
            "ready",

        "data_source":
            "real_tmap_moct_link",

        "tmap_api_called":
            False,

        "success_od_count":
            int(
                len(
                    success_od
                )
            ),

        "route_candidate_count":
            int(
                len(
                    routes
                )
            ),

        "mapped_route_count":
            int(
                len(
                    mapped_routes
                )
            ),

        "usable_route_count":
            int(
                len(
                    usable_routes
                )
            ),

        "route_link_row_count":
            int(
                len(
                    links
                )
            ),

        "unique_link_count":
            unique_links,

        "traffic_source_distribution":
            traffic_source,

        "export_summary":
            summary,

    })


# ============================================================
# 특정 OD 상세 조회
#
# 예:
#
# OD_000324
#
# 반환:
# - OD 정보
# - Route A/B/C
# ============================================================

def get_od_detail(
    od_id,
):

    _load_data()


    target_od = str(
        od_id
    ).strip()


    success_od = (
        _cache[
            "success_od"
        ]
    )


    routes = (
        _cache[
            "routes"
        ]
    )


    # ========================================================
    # OD 확인
    # ========================================================

    manifest_rows = success_od[

        success_od[
            "od_id"
        ]

        ==
        target_od

    ]


    if manifest_rows.empty:

        return None


    # ========================================================
    # 해당 OD의 Route A/B/C
    # ========================================================

    route_rows = routes[

        routes[
            "od_id"
        ]

        ==
        target_od

    ].copy()


    # ========================================================
    # A → B → C 순서 정렬
    # ========================================================

    if (

        not route_rows.empty

        and

        "candidate_id"
        in
        route_rows.columns

    ):

        route_rows[
            "_candidate_order"
        ] = (

            route_rows[
                "candidate_id"
            ]

            .map(
                {

                    "A": 0,

                    "B": 1,

                    "C": 2,

                }
            )

            .fillna(
                99
            )

        )


        route_rows = (

            route_rows

            .sort_values(
                "_candidate_order"
            )

            .drop(
                columns=[
                    "_candidate_order"
                ]
            )

        )


    return _json_safe({

        "od":
            _records(
                manifest_rows
            )[0],

        "routes":
            _records(
                route_rows
            ),

    })


# ============================================================
# 특정 Route 상세 조회
#
# 예:
#
# OD_000324_A
# ============================================================

def get_integration_route(
    route_id,
):

    _load_data()


    target_route = str(
        route_id
    ).strip()


    routes = (
        _cache[
            "routes"
        ]
    )


    rows = routes[

        routes[
            "route_id"
        ]

        ==
        target_route

    ]


    if rows.empty:

        return None


    return _records(
        rows
    )[0]


# ============================================================
# 특정 Route의 LINK Sequence 조회
#
# 예:
#
# OD_000324_A
#
# 반환:
# - Route 정보
# - LINK 개수
# - 순서가 보존된 LINK 목록
# ============================================================

def get_integration_route_links(
    route_id,
):

    _load_data()


    target_route = str(
        route_id
    ).strip()


    routes = (
        _cache[
            "routes"
        ]
    )


    links = (
        _cache[
            "links"
        ]
    )


    # ========================================================
    # Route 존재 확인
    # ========================================================

    route_rows = routes[

        routes[
            "route_id"
        ]

        ==
        target_route

    ]


    if route_rows.empty:

        return None


    # ========================================================
    # 해당 Route의 LINK
    # ========================================================

    link_rows = links[

        links[
            "route_id"
        ]

        ==
        target_route

    ].copy()


    # ========================================================
    # LINK 순서 정렬
    # ========================================================

    if (

        not link_rows.empty

        and

        "link_order"
        in
        link_rows.columns

    ):

        link_rows = (

            link_rows

            .sort_values(
                "link_order"
            )

        )


    route_record = (

        _records(
            route_rows
        )[0]

    )


    return _json_safe({

        "route":
            route_record,

        "link_count":
            int(
                len(
                    link_rows
                )
            ),

        "links":
            _records(
                link_rows
            ),

    })


# ============================================================
# 특정 Route의 실제 TMAP Geometry 조회
#
# 예:
#
# OD_000324_A
#
# 원본:
# data/routes/od_pipeline/OD_000324.json
#
# 원본 TMAP 좌표 형식:
#
# [longitude, latitude]
#
# 중요:
# TMAP API를 새로 호출하지 않는다.
# 저장된 JSON에서 Geometry만 읽는다.
# ============================================================

def get_integration_route_geometry(
    route_id,
):

    _load_data()


    target_route = str(
        route_id
    ).strip()


    routes = (
        _cache[
            "routes"
        ]
    )


    # ========================================================
    # 1. Route Catalog에서 Route 존재 확인
    # ========================================================

    route_rows = routes[

        routes[
            "route_id"
        ]

        ==
        target_route

    ]


    if route_rows.empty:

        return None


    route_record = (

        _records(
            route_rows
        )[0]

    )


    od_id = str(

        route_record.get(
            "od_id"
        )

    ).strip()


    candidate_id = str(

        route_record.get(
            "candidate_id"
        )

    ).strip().upper()


    # ========================================================
    # 2. 원본 OD JSON
    # ========================================================

    od_json_file = (

        OD_PIPELINE_DIR

        / f"{od_id}.json"

    )


    if not od_json_file.exists():

        raise FileNotFoundError(

            "원본 OD JSON 파일을 찾을 수 없습니다.\n"

            f"{od_json_file}"

        )


    # ========================================================
    # 3. JSON 읽기
    # ========================================================

    with open(

        od_json_file,

        "r",

        encoding="utf-8",

    ) as file:

        data = json.load(
            file
        )


    # ========================================================
    # 4. 성공 OD인지 확인
    # ========================================================

    batch_status = str(

        data.get(
            "batch_status",
            ""
        )

    ).strip().lower()


    if (
        batch_status
        !=
        "success"
    ):

        return None


    # ========================================================
    # 5. Route 후보 목록
    # ========================================================

    pipeline_result = (

        data.get(
            "pipeline_result"
        )

        or

        {}

    )


    original_routes = (

        pipeline_result.get(
            "routes"
        )

        or

        []

    )


    if not isinstance(
        original_routes,
        list,
    ):

        return None


    # ========================================================
    # 6. A / B / C 중 요청 Route 찾기
    # ========================================================

    matched_route = None


    for route in original_routes:

        if not isinstance(
            route,
            dict,
        ):

            continue


        current_candidate = str(

            route.get(
                "candidate_id",
                ""
            )

        ).strip().upper()


        if (
            current_candidate
            ==
            candidate_id
        ):

            matched_route = route

            break


    if matched_route is None:

        return None


    # ========================================================
    # 7. 실제 TMAP Geometry
    #
    # 원본:
    # [
    #   [127.x, 37.x],
    #   [127.x, 37.x],
    #   ...
    # ]
    #
    # = [longitude, latitude]
    # ========================================================

    geometry = (

        matched_route.get(
            "geometry"
        )

        or

        []

    )


    clean_geometry = []


    if isinstance(
        geometry,
        list,
    ):

        for point in geometry:

            if (

                not isinstance(
                    point,
                    (list, tuple),
                )

                or

                len(
                    point
                )
                <
                2

            ):

                continue


            try:

                lon = float(
                    point[0]
                )


                lat = float(
                    point[1]
                )

            except (
                TypeError,
                ValueError,
            ):

                continue


            # ------------------------------------------------
            # 기본적인 좌표 유효성 확인
            # ------------------------------------------------

            if not (
                -180.0
                <=
                lon
                <=
                180.0
            ):

                continue


            if not (
                -90.0
                <=
                lat
                <=
                90.0
            ):

                continue


            clean_geometry.append(
                [
                    lon,
                    lat,
                ]
            )


    # ========================================================
    # 8. 출발지 / 목적지
    # ========================================================

    origin = (

        matched_route.get(
            "origin"
        )

        or

        {}

    )


    destination = (

        matched_route.get(
            "destination"
        )

        or

        {}

    )


    # ========================================================
    # 9. 결과 반환
    # ========================================================

    return _json_safe({

        "route_id":
            target_route,

        "od_id":
            od_id,

        "candidate_id":
            candidate_id,

        "route_label":
            matched_route.get(
                "route_label"
            ),

        "search_option":
            matched_route.get(
                "search_option"
            ),

        "source":
            matched_route.get(
                "source"
            ),

        "total_distance_m":
            matched_route.get(
                "total_distance_m"
            ),

        "tmap_eta_sec":
            matched_route.get(
                "tmap_eta_sec"
            ),

        "tmap_eta_min":
            matched_route.get(
                "tmap_eta_min"
            ),

        "origin": {

            "name":
                origin.get(
                    "name"
                ),

            "lat":
                origin.get(
                    "lat"
                ),

            "lon":
                origin.get(
                    "lon"
                ),

        },

        "destination": {

            "name":
                destination.get(
                    "name"
                ),

            "lat":
                destination.get(
                    "lat"
                ),

            "lon":
                destination.get(
                    "lon"
                ),

        },

        # ----------------------------------------------------
        # Flutter에서 헷갈리지 않도록 명시
        # ----------------------------------------------------

        "coordinate_order":
            "lon_lat",

        "point_count":
            int(
                len(
                    clean_geometry
                )
            ),

        "geometry":
            clean_geometry,

        # ----------------------------------------------------
        # API 호출 여부 명시
        # ----------------------------------------------------

        "tmap_api_called":
            False,

    })