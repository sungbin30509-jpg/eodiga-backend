from pathlib import Path
import json

import pandas as pd


# ============================================================
# FLOW:MATE
# Evaluation Plan Builder
#
# 역할
# ------------------------------------------------------------
# 사용자별 출발시간 후보
#        +
# 완료된 OD의 사용 가능한 Route A/B/C
#        ↓
# user × departure_time × route_candidate
#
# 평가 조합을 생성한다.
#
#
# 사용 가능한 Mapping Quality
# ------------------------------------------------------------
# good       → 사용
# recovered  → 사용
# review     → 사용
# poor       → 제외
# failed     → 제외
#
#
# 주의
# ------------------------------------------------------------
# 아직 Route Batch가 완료되지 않은 OD는 제외한다.
# 600 OD가 모두 완료된 후 다시 실행하면
# 최종 Evaluation Plan을 만들 수 있다.
#
# 여기서는 미래속도 / 혼잡 / 추천점수를 계산하지 않는다.
# "앞으로 무엇을 평가할 것인지"만 정의한다.
# ============================================================


# ============================================================
# 1. 프로젝트 경로
# ============================================================

ROOT = Path(__file__).resolve().parents[2]


# ============================================================
# 2. 입력 파일
# ============================================================

DEPARTURE_FILE = (
    ROOT
    / "data"
    / "generated"
    / "user_departure_candidates_with_od.csv"
)


OD_RESULT_DIR = (
    ROOT
    / "data"
    / "routes"
    / "od_pipeline"
)


# ============================================================
# 3. 출력 파일
# ============================================================

OUTPUT_FILE = (
    ROOT
    / "data"
    / "generated"
    / "evaluation_plan.csv"
)


SUMMARY_FILE = (
    ROOT
    / "data"
    / "generated"
    / "evaluation_plan_summary.json"
)


ROUTE_CATALOG_FILE = (
    ROOT
    / "data"
    / "generated"
    / "available_od_routes.csv"
)


# ============================================================
# 4. 평가에 사용할 Mapping Quality
# ============================================================

ALLOWED_MAPPING_QUALITIES = {

    "good",

    "recovered",

    "review",

}


# ============================================================
# 5. 문자열 정리
# ============================================================

def clean_text(
    value,
    default="",
):

    if value is None:

        return default


    try:

        if pd.isna(
            value
        ):

            return default

    except Exception:

        pass


    return str(
        value
    ).strip()


# ============================================================
# 6. 완료된 OD에서 사용 가능한 Route 추출
# ============================================================

def extract_available_routes():

    files = sorted(

        OD_RESULT_DIR.glob(
            "OD_*.json"
        )

    )


    route_rows = []

    loaded_od_ids = set()

    skipped_files = 0

    excluded_poor_count = 0

    excluded_failed_count = 0


    # ========================================================
    # OD JSON 순회
    # ========================================================

    for file_path in files:

        # ----------------------------------------------------
        # Batch가 동시에 결과 파일을 쓰고 있을 수 있으므로
        # 읽기 실패 파일은 안전하게 Skip
        # ----------------------------------------------------

        try:

            with open(
                file_path,
                "r",
                encoding="utf-8",
            ) as file:

                data = json.load(
                    file
                )

        except Exception as error:

            print(

                "⚠️ OD 파일 읽기 Skip:",

                file_path.name,

                "|",

                type(
                    error
                ).__name__,

            )

            skipped_files += 1

            continue


        # ====================================================
        # OD ID
        # ====================================================

        od_id = clean_text(

            data.get(
                "od_id"
            )

            or

            file_path.stem

        )


        # ====================================================
        # Pipeline Result
        # ====================================================

        pipeline_result = (

            data.get(
                "pipeline_result"
            )

            or

            {}

        )


        if not isinstance(
            pipeline_result,
            dict,
        ):

            continue


        # ====================================================
        # Route A/B/C
        # ====================================================

        routes = (

            pipeline_result.get(
                "routes",
                [],
            )

        )


        if not isinstance(
            routes,
            list,
        ):

            continue


        has_usable_route = False


        # ====================================================
        # 각 Route 후보 확인
        # ====================================================

        for route in routes:

            if not isinstance(
                route,
                dict,
            ):

                continue


            candidate_id = clean_text(

                route.get(
                    "candidate_id"
                )

            )


            if not candidate_id:

                continue


            # =================================================
            # LINK Mapping 결과
            # =================================================

            mapping = (

                route.get(
                    "link_mapping_v2",
                    {},
                )

            )


            if not isinstance(
                mapping,
                dict,
            ):

                continue


            # =================================================
            # Mapping Status
            # =================================================

            status = clean_text(

                mapping.get(
                    "status"
                )

            ).lower()


            # -------------------------------------------------
            # failed 등의 Route는 제외
            # -------------------------------------------------

            if status != "mapped":

                excluded_failed_count += 1

                continue


            # =================================================
            # Mapping Quality
            # =================================================

            quality = clean_text(

                mapping.get(
                    "quality"
                )

            ).lower()


            # -------------------------------------------------
            # Evaluation Plan 허용 품질
            #
            # good       → 사용
            # recovered  → 사용
            # review     → 사용
            # poor       → 제외
            # -------------------------------------------------

            if (

                quality

                not in

                ALLOWED_MAPPING_QUALITIES

            ):

                excluded_poor_count += 1

                continue


            has_usable_route = True


            # =================================================
            # Route 기본 정보
            # =================================================

            route_distance_m = (

                route.get(
                    "total_distance_m"
                )

                or

                route.get(
                    "distance_m"
                )

                or

                route.get(
                    "totalDistance"
                )

            )


            route_time_sec = (

                route.get(
                    "total_time_sec"
                )

                or

                route.get(
                    "duration_sec"
                )

                or

                route.get(
                    "totalTime"
                )

            )


            # =================================================
            # Route Catalog 한 행
            # =================================================

            route_rows.append({

                "od_id":
                    od_id,

                "route_candidate_id":
                    candidate_id,

                "mapping_quality":
                    quality,

                "mapping_search_mode":
                    clean_text(

                        mapping.get(
                            "search_mode"
                        )

                    ),

                "mapping_coverage_percent":
                    mapping.get(
                        "coverage_percent"
                    ),

                "mapping_connectivity_percent":
                    mapping.get(
                        "connectivity_percent"
                    ),

                "mapping_length_ratio":
                    mapping.get(
                        "length_ratio"
                    ),

                "matched_link_count":
                    mapping.get(
                        "matched_link_count"
                    ),

                "route_distance_m":
                    route_distance_m,

                "route_time_sec":
                    route_time_sec,

            })


        # ====================================================
        # 하나 이상의 Route가 usable이면 OD 사용 가능
        # ====================================================

        if has_usable_route:

            loaded_od_ids.add(
                od_id
            )


    # ========================================================
    # DataFrame
    # ========================================================

    route_catalog = pd.DataFrame(
        route_rows
    )


    return (

        route_catalog,

        loaded_od_ids,

        len(
            files
        ),

        skipped_files,

        excluded_poor_count,

        excluded_failed_count,

    )


# ============================================================
# 7. Evaluation Plan 생성
# ============================================================

def build_evaluation_plan():

    print()

    print(
        "========================================"
    )

    print(
        "FLOW:MATE Evaluation Plan Builder"
    )

    print(
        "========================================"
    )


    # ========================================================
    # 입력 파일 확인
    # ========================================================

    if not DEPARTURE_FILE.exists():

        raise FileNotFoundError(

            "출발시간 + OD 파일을 찾을 수 없습니다.\n"
            f"{DEPARTURE_FILE}"

        )


    if not OD_RESULT_DIR.exists():

        raise FileNotFoundError(

            "OD Route 결과 폴더를 찾을 수 없습니다.\n"
            f"{OD_RESULT_DIR}"

        )


    # ========================================================
    # 출발시간 후보 읽기
    # ========================================================

    departure = pd.read_csv(

        DEPARTURE_FILE,

        dtype={

            "user_id":
                str,

            "od_id":
                str,

            "origin_location_id":
                str,

            "destination_location_id":
                str,

        },

    )


    # ========================================================
    # 필수 컬럼 확인
    # ========================================================

    required_columns = {

        "user_id",

        "od_id",

        "candidate_departure_time",

        "planned_departure_time",

        "offset_minutes",

    }


    missing_columns = (

        required_columns

        -

        set(
            departure.columns
        )

    )


    if missing_columns:

        raise ValueError(

            "출발시간 후보 파일에 필수 컬럼이 없습니다: "

            f"{sorted(missing_columns)}"

        )


    print(

        "전체 출발시간 후보:",

        f"{len(departure):,}",

    )


    print(

        "전체 사용자:",

        f"{departure['user_id'].nunique():,}",

    )


    print(

        "전체 OD:",

        f"{departure['od_id'].nunique():,}",

    )


    # ========================================================
    # 현재 사용 가능한 OD Route 불러오기
    # ========================================================

    (
        route_catalog,

        loaded_od_ids,

        od_file_count,

        skipped_file_count,

        excluded_poor_count,

        excluded_failed_count,

    ) = extract_available_routes()


    # ========================================================
    # Route가 하나도 없을 경우
    # ========================================================

    if route_catalog.empty:

        raise RuntimeError(

            "현재 Evaluation에 사용할 수 있는 "
            "OD Route가 없습니다."

        )


    print()

    print(

        "현재 OD 결과 파일:",

        od_file_count,

    )


    print(

        "사용 가능한 OD:",

        len(
            loaded_od_ids
        ),

    )


    print(

        "사용 가능한 Route 후보:",

        len(
            route_catalog
        ),

    )


    print(

        "읽기 Skip 파일:",

        skipped_file_count,

    )


    print(

        "품질 제외 Route:",

        excluded_poor_count,

    )


    print(

        "Mapping 실패 Route:",

        excluded_failed_count,

    )


    # ========================================================
    # 중복 Route 검사
    #
    # 같은 OD의 같은 A/B/C가 두 번 존재하면 안 됨
    # ========================================================

    duplicated_routes = (

        route_catalog

        .duplicated(

            subset=[

                "od_id",

                "route_candidate_id",

            ]

        )

        .sum()

    )


    if duplicated_routes > 0:

        raise RuntimeError(

            "Route Catalog에 "

            f"{duplicated_routes}개의 중복 "

            "OD + Route 후보가 있습니다."

        )


    # ========================================================
    # Route Catalog 정렬
    # ========================================================

    route_catalog = (

        route_catalog

        .sort_values(

            by=[

                "od_id",

                "route_candidate_id",

            ]

        )

        .reset_index(
            drop=True
        )

    )


    # ========================================================
    # Route Catalog 저장
    # ========================================================

    ROUTE_CATALOG_FILE.parent.mkdir(

        parents=True,

        exist_ok=True,

    )


    route_catalog.to_csv(

        ROUTE_CATALOG_FILE,

        index=False,

        encoding="utf-8-sig",

    )


    # ========================================================
    # 현재 Route가 준비된 OD의 출발시간 후보
    # ========================================================

    available_departure = (

        departure[

            departure[
                "od_id"
            ].isin(
                loaded_od_ids
            )

        ]

        .copy()

    )


    # ========================================================
    # 아직 Route가 준비되지 않은 OD
    # ========================================================

    waiting_departure = (

        departure[

            ~departure[
                "od_id"
            ].isin(
                loaded_od_ids
            )

        ]

        .copy()

    )


    # ========================================================
    # user
    # × departure time
    # × Route A/B/C
    #
    # od_id 기준 Join
    # ========================================================

    evaluation_plan = (

        available_departure

        .merge(

            route_catalog,

            on="od_id",

            how="inner",

            validate="many_to_many",

        )

    )


    # ========================================================
    # index 정리
    # ========================================================

    evaluation_plan = (

        evaluation_plan

        .reset_index(
            drop=True
        )

    )


    # ========================================================
    # Evaluation ID 생성
    # ========================================================

    evaluation_plan.insert(

        0,

        "evaluation_id",

        [

            f"EVAL_{index + 1:09d}"

            for index
            in range(
                len(
                    evaluation_plan
                )
            )

        ],

    )


    # ========================================================
    # Evaluation ID 중복 검사
    # ========================================================

    duplicated_evaluation_id = (

        evaluation_plan[
            "evaluation_id"
        ]

        .duplicated()

        .sum()

    )


    if duplicated_evaluation_id > 0:

        raise RuntimeError(

            "evaluation_id가 중복되었습니다."

        )


    # ========================================================
    # 같은 평가 조합 중복 검사
    #
    # user
    # + departure time
    # + OD
    # + Route
    # ========================================================

    evaluation_key_columns = [

        "user_id",

        "od_id",

        "candidate_departure_time",

        "route_candidate_id",

    ]


    duplicate_evaluation_rows = (

        evaluation_plan

        .duplicated(

            subset=(
                evaluation_key_columns
            )

        )

        .sum()

    )


    if duplicate_evaluation_rows > 0:

        raise RuntimeError(

            "동일한 Evaluation 조합이 "

            f"{duplicate_evaluation_rows}개 중복되었습니다."

        )


    # ========================================================
    # 출력 저장
    # ========================================================

    OUTPUT_FILE.parent.mkdir(

        parents=True,

        exist_ok=True,

    )


    evaluation_plan.to_csv(

        OUTPUT_FILE,

        index=False,

        encoding="utf-8-sig",

    )


    # ========================================================
    # 통계
    # ========================================================

    available_user_count = int(

        available_departure[
            "user_id"
        ]

        .nunique()

    )


    available_od_count = int(

        available_departure[
            "od_id"
        ]

        .nunique()

    )


    waiting_od_count = int(

        waiting_departure[
            "od_id"
        ]

        .nunique()

    )


    waiting_user_count = int(

        waiting_departure[
            "user_id"
        ]

        .nunique()

    )


    route_quality_distribution = (

        route_catalog[
            "mapping_quality"
        ]

        .value_counts()

        .to_dict()

    )


    route_quality_distribution = {

        str(
            key
        ):
            int(
                value
            )

        for key, value
        in route_quality_distribution.items()

    }


    route_count_per_od = (

        route_catalog

        .groupby(
            "od_id"
        )

        .size()

    )


    min_routes_per_od = int(

        route_count_per_od.min()

    )


    max_routes_per_od = int(

        route_count_per_od.max()

    )


    average_routes_per_od = float(

        route_count_per_od.mean()

    )


    # ========================================================
    # Summary
    # ========================================================

    summary = {

        "total_departure_candidate_rows":
            int(
                len(
                    departure
                )
            ),

        "available_departure_candidate_rows":
            int(
                len(
                    available_departure
                )
            ),

        "waiting_departure_candidate_rows":
            int(
                len(
                    waiting_departure
                )
            ),

        "available_user_count":
            available_user_count,

        "waiting_user_count":
            waiting_user_count,

        "available_od_count":
            available_od_count,

        "waiting_od_count":
            waiting_od_count,

        "available_route_candidate_count":
            int(
                len(
                    route_catalog
                )
            ),

        "evaluation_row_count":
            int(
                len(
                    evaluation_plan
                )
            ),

        "min_routes_per_od":
            min_routes_per_od,

        "max_routes_per_od":
            max_routes_per_od,

        "average_routes_per_od":
            round(
                average_routes_per_od,
                3,
            ),

        "route_quality_distribution":
            route_quality_distribution,

        "excluded_quality_route_count":
            excluded_poor_count,

        "excluded_failed_route_count":
            excluded_failed_count,

        "allowed_mapping_qualities":
            sorted(
                ALLOWED_MAPPING_QUALITIES
            ),

        "route_catalog_file":
            str(
                ROUTE_CATALOG_FILE
            ),

        "evaluation_plan_file":
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
        "Evaluation Plan 결과"
    )

    print(
        "========================================"
    )


    print(

        "현재 사용 가능한 사용자:",

        f"{available_user_count:,}",

    )


    print(

        "아직 Route 대기 사용자:",

        f"{waiting_user_count:,}",

    )


    print(

        "현재 사용 가능한 OD:",

        f"{available_od_count:,}",

    )


    print(

        "아직 Route 대기 OD:",

        f"{waiting_od_count:,}",

    )


    print(

        "현재 Route 후보:",

        f"{len(route_catalog):,}",

    )


    print(

        "Evaluation 조합:",

        f"{len(evaluation_plan):,}",

    )


    print()

    print(
        "OD당 Route 후보:"
    )


    print(

        "  최소:",

        min_routes_per_od,

    )


    print(

        "  최대:",

        max_routes_per_od,

    )


    print(

        "  평균:",

        round(
            average_routes_per_od,
            2,
        ),

    )


    print()

    print(
        "Mapping Quality:"
    )


    for (
        quality,
        count,
    ) in route_quality_distribution.items():

        print(

            f"  {quality}:",

            f"{count:,}",

        )


    print()

    print(

        "평가 제외 품질 Route:",

        excluded_poor_count,

    )


    print(

        "Mapping 실패 Route:",

        excluded_failed_count,

    )


    print()

    print(
        "Route Catalog:"
    )


    print(
        ROUTE_CATALOG_FILE
    )


    print()

    print(
        "Evaluation Plan:"
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
        "Evaluation Plan 생성 완료"
    )

    print(
        "========================================"
    )


    return evaluation_plan


# ============================================================
# 8. 직접 실행
# ============================================================

if __name__ == "__main__":

    build_evaluation_plan()