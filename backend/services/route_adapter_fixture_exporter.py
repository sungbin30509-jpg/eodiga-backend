from pathlib import Path
import json
import shutil

from backend.services.route_adapter import (
    load_json,
    adapt_route_result,
    NODE_LINK_DATASET,
)


# ============================================================
# FLOW:MATE
# Route Adapter Gateway Fixture Exporter
#
# 실제 저장된 TMAP + MOCT_LINK 결과에서
# usable Route 0 / 1 / 2 / 3개 사례를 추출한다.
#
# TMAP API 호출 없음
# Mock Route 생성 없음
# ============================================================


ROOT = Path(__file__).resolve().parents[2]


VALIDATION_SUMMARY_PATH = (
    ROOT
    / "data"
    / "adapter_validation"
    / "route_adapter_validation_summary_v2.json"
)


OD_PIPELINE_DIR = (
    ROOT
    / "data"
    / "routes"
    / "od_pipeline"
)


OUTPUT_DIR = (
    ROOT
    / "data"
    / "team_share"
    / "gateway_fixtures"
)


RAW_SOURCE_DIR = (
    OUTPUT_DIR
    / "raw_sources"
)


# ============================================================
# JSON 저장
# ============================================================

def save_json(data, path):

    path = Path(path)

    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    with open(
        path,
        "w",
        encoding="utf-8",
    ) as file:

        json.dump(
            data,
            file,
            ensure_ascii=False,
            indent=2,
        )


# ============================================================
# README 생성
#
# 삼중 따옴표를 사용하지 않아서
# 복붙 시 문자열 오류가 나지 않게 구성
# ============================================================

def build_readme(manifest):

    fixtures = manifest.get(
        "fixtures",
        {}
    )


    lines = [

        "# FLOW:MATE Gateway Fixtures",
        "",

        "실제 TMAP Route + MOCT_LINK Map Matching 결과를",
        "Route Adapter v2로 변환한 Integration Gateway 테스트 자료입니다.",
        "",

        "새로운 TMAP API 호출이나 Mock Route 생성은 하지 않았습니다.",
        "",

        "## 실제 Fixture",
        "",

    ]


    for route_count in (
        "0",
        "1",
        "2",
        "3",
    ):

        fixture = fixtures.get(
            route_count,
            {}
        )


        if fixture.get(
            "found"
        ):

            lines.append(

                f"- {route_count} Route: "
                f"{fixture.get('od_id')} "
                f"(status={fixture.get('adapter_status')})"

            )

        else:

            lines.append(

                f"- {route_count} Route: NOT FOUND"

            )


    lines.extend([

        "",
        "## Mapping Quality 정책",
        "",

        "- good → 사용",
        "- recovered → 사용",
        "- review → 사용",
        "- poor → 제외",
        "- failed → 제외",
        "",

        "서비스 사용 여부는 mapping status가 아니라 quality를 기준으로 판단합니다.",
        "",

        "## 0 Route 계약",
        "",

        "사용 가능한 Route가 하나도 없는 경우에도 Adapter 오류로 처리하지 않습니다.",
        "",

        "status = no_usable_routes",
        "routes = []",
        "",

        "제외된 후보는 excluded_routes에 유지합니다.",
        "",

        "## Core Route 계약",
        "",

        "Route",
        "- route_id",
        "- origin_location_id",
        "- destination_location_id",
        "- links",
        "",

        "RouteLink",
        "- LINK_ID",
        "- link_order",
        "- link_length_m",
        "",

        "## route_id 규칙",
        "",

        "{od_id}_{candidate_id}",
        "",

        "예:",
        "- OD_000004_A",
        "- OD_000004_B",
        "",

        "## Location ID",
        "",

        "기존 Synthetic OD와 연결 가능한 경우 기존 location_id를 유지합니다.",
        "TMAP poi_id를 내부 location_id로 직접 사용하지 않습니다.",
        "",

        "## Metadata",
        "",

        "아래 정보는 side metadata로 유지합니다.",
        "",

        "- Mapping status / quality",
        "- search mode",
        "- coverage / connectivity",
        "- matched LINK count",
        "- broken connections",
        "- recovery 여부",
        "- virtual bridge 정보",
        "- TMAP 원본 Route 거리",
        "- matched geometry 길이",
        "- mapped LINK 길이 합",
        "- residual distance",
        "- 성남 내부 / 외부 정보",
        "- duplicate LINK 여부",
        "- NODE/LINK 데이터 버전",
        "",

        "residual_distance_m이 coverage_estimate이면",
        "현재 단계에서는 ETA 계산값으로 확정하지 않습니다.",
        "",

        "## NODE/LINK",
        "",

        NODE_LINK_DATASET,
        "",

    ])


    return "\n".join(
        lines
    )


# ============================================================
# Fixture Export
# ============================================================

def export_gateway_fixtures():

    # --------------------------------------------------------
    # Validator 결과 확인
    # --------------------------------------------------------

    if not VALIDATION_SUMMARY_PATH.exists():

        raise FileNotFoundError(

            "Validator v2 summary 파일을 찾을 수 없습니다.\n"
            f"{VALIDATION_SUMMARY_PATH}\n\n"
            "먼저 아래 명령을 실행하세요:\n"
            "python -m backend.services.route_adapter_validator"

        )


    # --------------------------------------------------------
    # OD Pipeline 폴더 확인
    # --------------------------------------------------------

    if not OD_PIPELINE_DIR.exists():

        raise FileNotFoundError(

            "OD Pipeline 폴더를 찾을 수 없습니다.\n"
            f"{OD_PIPELINE_DIR}"

        )


    # --------------------------------------------------------
    # 출력 폴더 생성
    # --------------------------------------------------------

    OUTPUT_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )


    RAW_SOURCE_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )


    # --------------------------------------------------------
    # Validator Summary 읽기
    # --------------------------------------------------------

    validation_summary = (
        load_json(
            VALIDATION_SUMMARY_PATH
        )
    )


    examples = (
        validation_summary.get(
            "examples_by_usable_route_count",
            {}
        )
    )


    # --------------------------------------------------------
    # Manifest
    # --------------------------------------------------------

    manifest = {

        "package":
            "FLOWMATE_ROUTE_ADAPTER_GATEWAY_FIXTURES",

        "package_version":
            "1.0",

        "adapter_schema_version":
            "route_adapter_v2",

        "node_link_dataset":
            NODE_LINK_DATASET,

        "source":
            "actual_saved_tmap_moct_link_pipeline",

        "tmap_api_called":
            False,

        "mock_route_generated":
            False,

        "fixture_route_counts":
            [
                0,
                1,
                2,
                3,
            ],

        "fixtures":
            {},

    }


    # ========================================================
    # 0 / 1 / 2 / 3 Route 사례 추출
    # ========================================================

    for route_count in (
        "0",
        "1",
        "2",
        "3",
    ):

        od_id = examples.get(
            route_count
        )


        # ----------------------------------------------------
        # 해당 Route count 사례가 없는 경우
        # ----------------------------------------------------

        if not od_id:

            manifest[
                "fixtures"
            ][
                route_count
            ] = {

                "found":
                    False,

                "usable_route_count":
                    int(
                        route_count
                    ),

            }

            continue


        # ----------------------------------------------------
        # 원본 OD 파일
        # ----------------------------------------------------

        raw_path = (
            OD_PIPELINE_DIR
            / f"{od_id}.json"
        )


        if not raw_path.exists():

            manifest[
                "fixtures"
            ][
                route_count
            ] = {

                "found":
                    False,

                "od_id":
                    od_id,

                "usable_route_count":
                    int(
                        route_count
                    ),

                "error":
                    "raw_source_not_found",

            }

            continue


        # ----------------------------------------------------
        # 원본 Pipeline 읽기
        # ----------------------------------------------------

        raw_data = (
            load_json(
                raw_path
            )
        )


        # ----------------------------------------------------
        # Route Adapter 실행
        # ----------------------------------------------------

        adapted = (
            adapt_route_result(
                raw_data
            )
        )


        actual_route_count = len(

            adapted.get(
                "routes",
                []
            )

        )


        expected_route_count = int(
            route_count
        )


        # ----------------------------------------------------
        # Validator 결과와 현재 Adapter 결과 일치 확인
        # ----------------------------------------------------

        if (
            actual_route_count
            !=
            expected_route_count
        ):

            raise ValueError(

                f"{od_id}: "
                f"Validator 예상 usable Route="
                f"{expected_route_count}, "
                f"현재 Adapter 결과="
                f"{actual_route_count}"

            )


        # ----------------------------------------------------
        # Fixture 저장
        # ----------------------------------------------------

        fixture_filename = (

            f"fixture_"
            f"{route_count}"
            f"_routes_"
            f"{od_id}"
            f".json"

        )


        fixture_path = (
            OUTPUT_DIR
            / fixture_filename
        )


        save_json(
            adapted,
            fixture_path,
        )


        # ----------------------------------------------------
        # 원본 Pipeline도 같이 복사
        # ----------------------------------------------------

        raw_destination = (

            RAW_SOURCE_DIR
            / raw_path.name

        )


        shutil.copy2(
            raw_path,
            raw_destination,
        )


        # ----------------------------------------------------
        # Location 정보
        # ----------------------------------------------------

        location = (
            adapted.get(
                "location_resolution",
                {}
            )
        )


        # ----------------------------------------------------
        # Usable Route
        # ----------------------------------------------------

        usable_routes = (
            adapted.get(
                "routes",
                []
            )
        )


        usable_route_ids = [

            route.get(
                "route_id"
            )

            for route
            in usable_routes

        ]


        # ----------------------------------------------------
        # Excluded Route
        # ----------------------------------------------------

        excluded_routes = (
            adapted.get(
                "excluded_routes",
                []
            )
        )


        excluded_route_ids = [

            route.get(
                "route_id"
            )

            for route
            in excluded_routes

        ]


        # ----------------------------------------------------
        # Mapping Quality
        # ----------------------------------------------------

        route_metadata = (
            adapted.get(
                "route_metadata",
                {}
            )
        )


        mapping_qualities = {}


        for route_id in usable_route_ids:

            route_meta = (
                route_metadata.get(
                    route_id,
                    {}
                )
            )


            mapping = (
                route_meta.get(
                    "mapping",
                    {}
                )
            )


            mapping_qualities[
                route_id
            ] = (
                mapping.get(
                    "mapping_quality"
                )
            )


        # ----------------------------------------------------
        # Manifest 기록
        # ----------------------------------------------------

        manifest[
            "fixtures"
        ][
            route_count
        ] = {

            "found":
                True,

            "od_id":
                od_id,

            "fixture_file":
                fixture_filename,

            "raw_source_file":
                (
                    f"raw_sources/"
                    f"{raw_path.name}"
                ),

            "adapter_status":
                adapted.get(
                    "status"
                ),

            "usable_route_count":
                actual_route_count,

            "excluded_route_count":
                len(
                    excluded_routes
                ),

            "usable_route_ids":
                usable_route_ids,

            "excluded_route_ids":
                excluded_route_ids,

            "mapping_qualities":
                mapping_qualities,

            "origin_location_id":
                location.get(
                    "origin_location_id"
                ),

            "destination_location_id":
                location.get(
                    "destination_location_id"
                ),

            "location_resolution_source":
                location.get(
                    "resolution_source"
                ),

        }


    # ========================================================
    # Manifest 저장
    # ========================================================

    save_json(

        manifest,

        OUTPUT_DIR
        / "manifest.json",

    )


    # ========================================================
    # README 저장
    # ========================================================

    readme_text = (
        build_readme(
            manifest
        )
    )


    with open(

        OUTPUT_DIR
        / "README.md",

        "w",

        encoding="utf-8",

    ) as file:

        file.write(
            readme_text
        )


    return manifest


# ============================================================
# 실행
# ============================================================

def main():

    print()

    print(
        "=========================================="
    )

    print(
        "FLOW:MATE Gateway Fixture Exporter"
    )

    print(
        "=========================================="
    )

    print()


    manifest = (
        export_gateway_fixtures()
    )


    for route_count in (
        "0",
        "1",
        "2",
        "3",
    ):

        fixture = (

            manifest
            .get(
                "fixtures",
                {}
            )
            .get(
                route_count,
                {}
            )

        )


        if fixture.get(
            "found"
        ):

            print(

                f"{route_count} Route"
                f" -> {fixture.get('od_id')}"
                f" / status="
                f"{fixture.get('adapter_status')}"

            )


            print(

                "   usable:",

                fixture.get(
                    "usable_route_ids"
                ),

            )


            print(

                "   excluded:",

                fixture.get(
                    "excluded_route_ids"
                ),

            )


        else:

            print(

                f"{route_count} Route"
                " -> NOT FOUND"

            )


    print()

    print(
        "NODE/LINK:"
    )

    print(
        NODE_LINK_DATASET
    )

    print()

    print(
        "저장 완료:"
    )

    print(
        OUTPUT_DIR
    )

    print()

    print(
        "TMAP API 호출: 없음"
    )

    print(
        "Mock Route 생성: 없음"
    )

    print(
        "=========================================="
    )

    print()


if __name__ == "__main__":
    main()