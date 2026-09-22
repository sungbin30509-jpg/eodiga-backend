from pathlib import Path
import json

import pandas as pd


# ============================================================
# FLOW:MATE
# Baseline Original Route Assignment
#
# 역할
# ------------------------------------------------------------
# FLOW 개입 전 BEFORE 시나리오에서
# 각 OD가 사용할 기준 Route를 하나 결정한다.
#
# 규칙
# ------------------------------------------------------------
# 1. Route A 사용 가능 → A
# 2. A 불가 → B
# 3. A/B 불가 → C
# 4. 전부 불가 → baseline 제외
#
# 사용 가능 품질:
# good / recovered / review
#
# poor / failed는 제외
#
# 주의
# ------------------------------------------------------------
# 이것은 실제 사용자의 과거 경로 선택 데이터가 아니라
# MVP Baseline을 위한 명시적 모델 가정이다.
# ============================================================


ROOT = Path(__file__).resolve().parents[2]


# ============================================================
# 입력 / 출력
# ============================================================

OD_RESULT_DIR = (
    ROOT
    / "data"
    / "routes"
    / "od_pipeline"
)


OUTPUT_FILE = (
    ROOT
    / "data"
    / "generated"
    / "baseline_od_routes.csv"
)


SUMMARY_FILE = (
    ROOT
    / "data"
    / "generated"
    / "baseline_od_routes_summary.json"
)


# ============================================================
# 설정
# ============================================================

ALLOWED_QUALITIES = {
    "good",
    "recovered",
    "review",
}


ROUTE_PRIORITY = {
    "A": 0,
    "B": 1,
    "C": 2,
}


# ============================================================
# 문자열 정리
# ============================================================

def clean_text(
    value,
    default="",
):

    if value is None:
        return default

    try:
        if pd.isna(value):
            return default
    except Exception:
        pass

    return str(value).strip()


# ============================================================
# Route 거리 / 시간 읽기
# ============================================================

def get_route_distance_m(
    route,
):

    values = [

        route.get("total_distance_m"),

        route.get("distance_m"),

        route.get("totalDistance"),

    ]


    for value in values:

        if value is None:
            continue

        try:
            return float(value)
        except (TypeError, ValueError):
            continue


    return None


def get_route_time_sec(
    route,
):

    values = [

        route.get("total_time_sec"),

        route.get("duration_sec"),

        route.get("totalTime"),

    ]


    for value in values:

        if value is None:
            continue

        try:
            return float(value)
        except (TypeError, ValueError):
            continue


    return None


# ============================================================
# Baseline Route 생성
# ============================================================

def build_baseline_route_assignment():

    print()
    print("========================================")
    print("FLOW:MATE Baseline Route Assignment")
    print("========================================")


    if not OD_RESULT_DIR.exists():

        raise FileNotFoundError(
            "OD Route 결과 폴더를 찾을 수 없습니다.\n"
            f"{OD_RESULT_DIR}"
        )


    files = sorted(
        OD_RESULT_DIR.glob("OD_*.json")
    )


    if not files:

        raise RuntimeError(
            "OD 결과 JSON이 없습니다."
        )


    print(
        "현재 OD 결과 파일:",
        len(files),
    )


    rows = []

    skipped_read = 0
    no_usable_route_count = 0


    # ========================================================
    # OD 순회
    # ========================================================

    for file_path in files:

        try:

            with open(
                file_path,
                "r",
                encoding="utf-8",
            ) as file:

                data = json.load(file)

        except Exception as error:

            print(
                f"⚠️ 읽기 Skip: {file_path.name} | "
                f"{type(error).__name__}"
            )

            skipped_read += 1
            continue


        od_id = clean_text(
            data.get("od_id")
            or file_path.stem
        )


        user_count = int(
            data.get("user_count", 0)
            or 0
        )


        pipeline_result = (
            data.get("pipeline_result")
            or {}
        )


        routes = (
            pipeline_result.get("routes", [])
        )


        if not isinstance(routes, list):

            no_usable_route_count += 1
            continue


        usable_routes = []


        # ====================================================
        # 평가 가능한 Route 추출
        # ====================================================

        for route in routes:

            if not isinstance(route, dict):
                continue


            candidate_id = clean_text(
                route.get("candidate_id")
            ).upper()


            if candidate_id not in ROUTE_PRIORITY:
                continue


            mapping = (
                route.get(
                    "link_mapping_v2",
                    {},
                )
            )


            if not isinstance(mapping, dict):
                continue


            status = clean_text(
                mapping.get("status")
            ).lower()


            quality = clean_text(
                mapping.get("quality")
            ).lower()


            if status != "mapped":
                continue


            if quality not in ALLOWED_QUALITIES:
                continue


            usable_routes.append({

                "candidate_id":
                    candidate_id,

                "quality":
                    quality,

                "search_mode":
                    clean_text(
                        mapping.get(
                            "search_mode"
                        )
                    ),

                "coverage_percent":
                    mapping.get(
                        "coverage_percent"
                    ),

                "connectivity_percent":
                    mapping.get(
                        "connectivity_percent"
                    ),

                "length_ratio":
                    mapping.get(
                        "length_ratio"
                    ),

                "matched_link_count":
                    mapping.get(
                        "matched_link_count"
                    ),

                "route_distance_m":
                    get_route_distance_m(
                        route
                    ),

                "route_time_sec":
                    get_route_time_sec(
                        route
                    ),

            })


        # ====================================================
        # usable route 없음
        # ====================================================

        if not usable_routes:

            no_usable_route_count += 1
            continue


        # ====================================================
        # A → B → C 우선순위
        # ====================================================

        usable_routes.sort(
            key=lambda item:
            ROUTE_PRIORITY[
                item["candidate_id"]
            ]
        )


        selected = (
            usable_routes[0]
        )


        # ====================================================
        # 선택 이유
        # ====================================================

        if selected["candidate_id"] == "A":

            selection_reason = (
                "tmap_default_route_a"
            )

        else:

            selection_reason = (
                "default_route_unusable_fallback_"
                + selected[
                    "candidate_id"
                ].lower()
            )


        # ====================================================
        # 결과
        # ====================================================

        rows.append({

            "od_id":
                od_id,

            "user_count":
                user_count,

            "baseline_route_candidate_id":
                selected[
                    "candidate_id"
                ],

            "selection_reason":
                selection_reason,

            "mapping_quality":
                selected[
                    "quality"
                ],

            "mapping_search_mode":
                selected[
                    "search_mode"
                ],

            "mapping_coverage_percent":
                selected[
                    "coverage_percent"
                ],

            "mapping_connectivity_percent":
                selected[
                    "connectivity_percent"
                ],

            "mapping_length_ratio":
                selected[
                    "length_ratio"
                ],

            "matched_link_count":
                selected[
                    "matched_link_count"
                ],

            "route_distance_m":
                selected[
                    "route_distance_m"
                ],

            "route_time_sec":
                selected[
                    "route_time_sec"
                ],

            "baseline_assumption":
                (
                    "TMAP default Route A; "
                    "fallback B then C when unusable"
                ),

        })


    # ========================================================
    # DataFrame
    # ========================================================

    result = pd.DataFrame(rows)


    if result.empty:

        raise RuntimeError(
            "Baseline Route를 하나도 생성하지 못했습니다."
        )


    # ========================================================
    # OD 중복 검사
    # ========================================================

    duplicate_od = (
        result["od_id"]
        .duplicated()
        .sum()
    )


    if duplicate_od > 0:

        raise RuntimeError(
            f"Baseline Route에서 OD 중복 "
            f"{duplicate_od}개가 발견되었습니다."
        )


    result = (
        result
        .sort_values("od_id")
        .reset_index(drop=True)
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
    # 통계
    # ========================================================

    route_distribution = (

        result[
            "baseline_route_candidate_id"
        ]

        .value_counts()

        .sort_index()

        .to_dict()

    )


    quality_distribution = (

        result[
            "mapping_quality"
        ]

        .value_counts()

        .to_dict()

    )


    route_distribution = {

        str(key):
            int(value)

        for key, value
        in route_distribution.items()

    }


    quality_distribution = {

        str(key):
            int(value)

        for key, value
        in quality_distribution.items()

    }


    fallback_count = int(

        (
            result[
                "baseline_route_candidate_id"
            ]
            !=
            "A"
        ).sum()

    )


    # ========================================================
    # Summary
    # ========================================================

    summary = {

        "od_result_file_count":
            len(files),

        "baseline_od_count":
            int(len(result)),

        "skipped_read_count":
            skipped_read,

        "no_usable_route_count":
            no_usable_route_count,

        "route_distribution":
            route_distribution,

        "mapping_quality_distribution":
            quality_distribution,

        "route_a_count":
            int(
                (
                    result[
                        "baseline_route_candidate_id"
                    ]
                    ==
                    "A"
                ).sum()
            ),

        "fallback_route_count":
            fallback_count,

        "baseline_rule":
            (
                "Use Route A when usable; "
                "otherwise B, then C."
            ),

        "output_file":
            str(OUTPUT_FILE),

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
    print("Baseline Route 결과")
    print("========================================")


    print(
        "Baseline 생성 OD:",
        len(result),
    )


    print(
        "사용 가능한 Route 없음:",
        no_usable_route_count,
    )


    print(
        "읽기 Skip:",
        skipped_read,
    )


    print()
    print("Baseline Route 분포:")


    for route_id in [
        "A",
        "B",
        "C",
    ]:

        print(
            f"  Route {route_id}:",
            route_distribution.get(
                route_id,
                0,
            ),
        )


    print()
    print(
        "A 사용 불가 → B/C Fallback:",
        fallback_count,
    )


    print()
    print("Mapping Quality:")


    for quality, count in (
        quality_distribution.items()
    ):

        print(
            f"  {quality}:",
            count,
        )


    print()
    print("결과:")
    print(OUTPUT_FILE)


    print()
    print("Summary:")
    print(SUMMARY_FILE)


    print()
    print("========================================")
    print("Baseline Route Assignment 완료")
    print("========================================")


    return result


# ============================================================
# 직접 실행
# ============================================================

if __name__ == "__main__":

    build_baseline_route_assignment()