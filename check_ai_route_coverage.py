from pathlib import Path
import csv
import json


# ============================================================
# 1. 프로젝트 루트
# ============================================================

PROJECT_ROOT = (
    Path(__file__)
    .resolve()
    .parent
)


# ============================================================
# 2. Route 파일 위치
# ============================================================

ROUTE_DIR = (
    PROJECT_ROOT
    / "data"
    / "routes"
)


ROUTE_FILES = {

    "A":
        ROUTE_DIR
        / "route_A_v2.json",

    "B":
        ROUTE_DIR
        / "route_B_v2.json",

    "C":
        ROUTE_DIR
        / "route_C_v2.json",
}


# ============================================================
# 3. AI 지원 LINK 목록
# ============================================================

SUPPORTED_LINKS_FILE = (
    PROJECT_ROOT
    / "ai"
    / "FLOW_AI_INTEGRATION"
    / "supported_links.csv"
)


# ============================================================
# 4. 결과 저장 파일
# ============================================================

OUTPUT_FILE = (
    ROUTE_DIR
    / "ai_route_coverage.json"
)


# ============================================================
# LINK_ID 문자열 정규화
# ============================================================

def normalize_link_id(value):

    if value is None:

        return None


    text = str(
        value
    ).strip()


    # CSV에서 숫자가
    # 2050019200.0
    # 처럼 들어온 경우 대응
    if text.endswith(
        ".0"
    ):

        text = text[:-2]


    return text


# ============================================================
# CSV에서 LINK_ID 컬럼 찾기
# ============================================================

def find_link_column(
    fieldnames,
):

    candidates = [

        "link_id",
        "LINK_ID",
        "Link_ID",
        "linkId",
        "linkid",
    ]


    for candidate in candidates:

        if candidate in fieldnames:

            return candidate


    # --------------------------------------------------------
    # 이름이 조금 달라도
    # link + id가 같이 들어있으면 사용
    # --------------------------------------------------------

    for field in fieldnames:

        lower = field.lower()

        if (
            "link" in lower
            and
            "id" in lower
        ):

            return field


    raise ValueError(

        "supported_links.csv에서 "
        "LINK_ID 컬럼을 찾지 못했습니다.\n"
        f"현재 컬럼: {fieldnames}"
    )


# ============================================================
# AI 지원 LINK 읽기
# ============================================================

def load_supported_links():

    if not SUPPORTED_LINKS_FILE.exists():

        raise FileNotFoundError(

            "supported_links.csv를 "
            "찾을 수 없습니다.\n"
            f"{SUPPORTED_LINKS_FILE}"
        )


    supported = set()


    with open(
        SUPPORTED_LINKS_FILE,
        "r",
        encoding="utf-8-sig",
        newline="",
    ) as file:

        reader = csv.DictReader(
            file
        )


        if reader.fieldnames is None:

            raise ValueError(
                "supported_links.csv에 "
                "헤더가 없습니다."
            )


        link_column = (
            find_link_column(
                reader.fieldnames
            )
        )


        print(
            "AI LINK 컬럼:",
            link_column
        )


        for row in reader:

            link_id = (
                normalize_link_id(
                    row.get(
                        link_column
                    )
                )
            )


            if link_id:

                supported.add(
                    link_id
                )


    return supported


# ============================================================
# LINK 객체인지 확인
# ============================================================

def is_link_object(
    value,
):

    if not isinstance(
        value,
        dict,
    ):

        return False


    possible_keys = {

        "link_id",
        "LINK_ID",
        "Link_ID",
    }


    return any(

        key in value

        for key
        in possible_keys
    )


# ============================================================
# LINK 객체 list인지 확인
# ============================================================

def is_link_list(
    value,
):

    if not isinstance(
        value,
        list,
    ):

        return False


    if len(
        value
    ) == 0:

        return False


    link_object_count = sum(

        1

        for item
        in value

        if is_link_object(
            item
        )
    )


    # --------------------------------------------------------
    # 전체 원소 중 80% 이상이
    # LINK 객체라면 LINK 목록으로 인정
    # --------------------------------------------------------

    threshold = max(

        1,

        int(
            len(
                value
            )
            * 0.8
        ),
    )


    return (
        link_object_count
        >=
        threshold
    )


# ============================================================
# Route JSON에서 LINK 목록 탐색
#
# route_A_v2 등의 경우
#
# 최상위:
# link_mapping_v2
#
# 그 내부:
# links / final_links / path / ...
#
# 구조가 달라도 재귀 탐색
# ============================================================

def find_route_links(
    route_data,
):

    # ========================================================
    # 1차:
    # 예상되는 주요 위치 우선 확인
    # ========================================================

    preferred_top_keys = [

        "links",
        "route_links",
        "matched_links",
        "link_sequence",
        "link_mapping_v2",
        "link_mapping",
    ]


    preferred_nested_keys = [

        "links",
        "route_links",
        "matched_links",
        "final_links",
        "link_sequence",
        "sequence",
        "path",
        "matched_sequence",
        "link_path",
        "final_path",
        "matched_path",
    ]


    for top_key in preferred_top_keys:

        if top_key not in route_data:

            continue


        value = route_data[
            top_key
        ]


        # ----------------------------------------------------
        # 최상위 값 자체가 LINK list
        # ----------------------------------------------------

        if is_link_list(
            value
        ):

            print(
                "Route LINK 위치:",
                top_key
            )

            print(
                "찾은 LINK 수:",
                len(
                    value
                )
            )

            return value


        # ----------------------------------------------------
        # dict 내부 탐색
        # ----------------------------------------------------

        if isinstance(
            value,
            dict,
        ):

            for nested_key in preferred_nested_keys:

                nested_value = (
                    value.get(
                        nested_key
                    )
                )


                if is_link_list(
                    nested_value
                ):

                    print(
                        "Route LINK 위치:",
                        f"{top_key}.{nested_key}",
                    )

                    print(
                        "찾은 LINK 수:",
                        len(
                            nested_value
                        )
                    )

                    return nested_value


    # ========================================================
    # 2차:
    # JSON 전체 재귀 탐색
    # ========================================================

    candidates = []


    def recursive_search(
        value,
        path="root",
    ):

        # ----------------------------------------------------
        # 현재 값 자체가 LINK list인지
        # ----------------------------------------------------

        if is_link_list(
            value
        ):

            candidates.append(
                (
                    path,
                    value,
                )
            )

            return


        # ----------------------------------------------------
        # dict 내부 재귀
        # ----------------------------------------------------

        if isinstance(
            value,
            dict,
        ):

            for (
                key,
                child,
            ) in value.items():

                recursive_search(

                    child,

                    f"{path}.{key}",
                )


        # ----------------------------------------------------
        # list 내부 재귀
        #
        # geometry 좌표 숫자 배열은
        # dict/list일 때만 추가 탐색
        # ----------------------------------------------------

        elif isinstance(
            value,
            list,
        ):

            for (
                index,
                child,
            ) in enumerate(
                value
            ):

                if isinstance(
                    child,
                    (
                        dict,
                        list,
                    ),
                ):

                    recursive_search(

                        child,

                        f"{path}[{index}]",
                    )


    recursive_search(
        route_data
    )


    # ========================================================
    # 후보가 발견된 경우
    # ========================================================

    if candidates:

        # ----------------------------------------------------
        # 여러 목록이 발견되면
        # LINK 개수가 가장 많은 목록 선택
        # ----------------------------------------------------

        candidates.sort(

            key=lambda item:
                len(
                    item[1]
                ),

            reverse=True,
        )


        selected_path = (
            candidates[
                0
            ][
                0
            ]
        )


        selected_links = (
            candidates[
                0
            ][
                1
            ]
        )


        print(
            "Route LINK 자동 탐색 위치:",
            selected_path
        )


        print(
            "찾은 LINK 수:",
            len(
                selected_links
            )
        )


        return selected_links


    # ========================================================
    # 끝까지 못 찾은 경우
    # ========================================================

    raise ValueError(

        "Route JSON에서 LINK_ID를 가진 "
        "LINK 목록을 찾지 못했습니다.\n"
        f"최상위 키: {list(route_data.keys())}"
    )


# ============================================================
# LINK_ID 추출
# ============================================================

def get_link_id(
    link,
):

    candidates = [

        "link_id",
        "LINK_ID",
        "Link_ID",
    ]


    for key in candidates:

        if key in link:

            return normalize_link_id(
                link[
                    key
                ]
            )


    # --------------------------------------------------------
    # properties 내부까지 확인
    # --------------------------------------------------------

    properties = (
        link.get(
            "properties"
        )
    )


    if isinstance(
        properties,
        dict,
    ):

        for key in candidates:

            if key in properties:

                return normalize_link_id(
                    properties[
                        key
                    ]
                )


    return None


# ============================================================
# LINK 길이 추출
# ============================================================

def get_link_length_m(
    link,
):

    candidates = [

        "length_m",
        "LENGTH",
        "length",
        "link_length_m",
        "link_length",
    ]


    # --------------------------------------------------------
    # 직접 필드
    # --------------------------------------------------------

    for key in candidates:

        if key not in link:

            continue


        value = link[
            key
        ]


        if value is None:

            continue


        try:

            return float(
                value
            )

        except (
            TypeError,
            ValueError,
        ):

            pass


    # --------------------------------------------------------
    # properties 내부
    # --------------------------------------------------------

    properties = (
        link.get(
            "properties"
        )
    )


    if isinstance(
        properties,
        dict,
    ):

        for key in candidates:

            if key not in properties:

                continue


            value = properties[
                key
            ]


            try:

                return float(
                    value
                )

            except (
                TypeError,
                ValueError,
            ):

                pass


    return 0.0


# ============================================================
# 도로명 추출
# ============================================================

def get_road_name(
    link,
):

    candidates = [

        "road_name",
        "ROAD_NAME",
        "roadName",
    ]


    for key in candidates:

        value = link.get(
            key
        )

        if value:

            return str(
                value
            )


    properties = (
        link.get(
            "properties"
        )
    )


    if isinstance(
        properties,
        dict,
    ):

        for key in candidates:

            value = (
                properties.get(
                    key
                )
            )

            if value:

                return str(
                    value
                )


    return ""


# ============================================================
# Sequence 추출
# ============================================================

def get_sequence(
    link,
    default_index,
):

    candidates = [

        "sequence",
        "seq",
        "order",
        "index",
    ]


    for key in candidates:

        if key in link:

            try:

                return int(
                    link[
                        key
                    ]
                )

            except (
                TypeError,
                ValueError,
            ):

                pass


    return default_index


# ============================================================
# Route 하나 분석
# ============================================================

def analyze_route(
    route_name,
    route_file,
    supported_links,
):

    print()
    print(
        "----------------------------------------"
    )

    print(
        f"Route {route_name} 파일 읽는 중"
    )

    print(
        route_file
    )


    if not route_file.exists():

        raise FileNotFoundError(

            f"Route {route_name} 파일이 없습니다.\n"
            f"{route_file}"
        )


    with open(
        route_file,
        "r",
        encoding="utf-8",
    ) as file:

        route_data = json.load(
            file
        )


    # ========================================================
    # LINK 목록 찾기
    # ========================================================

    links = (
        find_route_links(
            route_data
        )
    )


    supported_items = []

    unsupported_items = []


    total_distance_m = 0.0

    supported_distance_m = 0.0


    # ========================================================
    # LINK 하나씩 확인
    # ========================================================

    for (
        index,
        link,
    ) in enumerate(
        links
    ):

        if not isinstance(
            link,
            dict,
        ):

            continue


        link_id = (
            get_link_id(
                link
            )
        )


        length_m = (
            get_link_length_m(
                link
            )
        )


        road_name = (
            get_road_name(
                link
            )
        )


        sequence = (
            get_sequence(
                link,
                index,
            )
        )


        total_distance_m += (
            length_m
        )


        ai_supported = (
            link_id
            in supported_links
        )


        item = {

            "sequence":
                sequence,

            "link_id":
                link_id,

            "road_name":
                road_name,

            "length_m":
                round(
                    length_m,
                    3,
                ),

            "ai_supported":
                ai_supported,
        }


        if ai_supported:

            supported_items.append(
                item
            )

            supported_distance_m += (
                length_m
            )


        else:

            unsupported_items.append(
                item
            )


    # ========================================================
    # 통계
    # ========================================================

    total_count = len(
        supported_items
    ) + len(
        unsupported_items
    )


    supported_count = len(
        supported_items
    )


    unsupported_count = len(
        unsupported_items
    )


    if total_count > 0:

        link_coverage_pct = (

            supported_count
            /
            total_count
            *
            100.0
        )

    else:

        link_coverage_pct = 0.0


    if total_distance_m > 0:

        distance_coverage_pct = (

            supported_distance_m
            /
            total_distance_m
            *
            100.0
        )

    else:

        distance_coverage_pct = 0.0


    # ========================================================
    # Route metadata
    # ========================================================

    route_id = route_data.get(
        "route_id",
        f"route_{route_name}",
    )


    candidate_id = route_data.get(
        "candidate_id",
        route_name,
    )


    result = {

        "route":
            route_name,

        "route_id":
            route_id,

        "candidate_id":
            candidate_id,

        "route_file":
            route_file.name,

        "total_link_count":
            total_count,

        "ai_supported_link_count":
            supported_count,

        "ai_unsupported_link_count":
            unsupported_count,

        "link_coverage_pct":
            round(
                link_coverage_pct,
                2,
            ),

        "total_distance_m":
            round(
                total_distance_m,
                2,
            ),

        "ai_supported_distance_m":
            round(
                supported_distance_m,
                2,
            ),

        "ai_unsupported_distance_m":
            round(
                (
                    total_distance_m
                    -
                    supported_distance_m
                ),
                2,
            ),

        "distance_coverage_pct":
            round(
                distance_coverage_pct,
                2,
            ),

        "supported_links":
            supported_items,

        "unsupported_links":
            unsupported_items,
    }


    return result


# ============================================================
# Route 결과 출력
# ============================================================

def print_route_result(
    result,
):

    print()
    print(
        "========================================"
    )

    print(
        f"Route {result['route']} AI Coverage"
    )

    print(
        "========================================"
    )


    print(
        "route_id:",
        result[
            "route_id"
        ],
    )


    print()


    print(
        "전체 LINK:",
        result[
            "total_link_count"
        ],
    )


    print(
        "AI 지원 LINK:",
        result[
            "ai_supported_link_count"
        ],
    )


    print(
        "AI 미지원 LINK:",
        result[
            "ai_unsupported_link_count"
        ],
    )


    print(
        "LINK 기준 Coverage:",
        f"{result['link_coverage_pct']:.2f}%"
    )


    print()


    print(
        "전체 경로 길이:",
        f"{result['total_distance_m'] / 1000:.3f} km"
    )


    print(
        "AI 지원 거리:",
        f"{result['ai_supported_distance_m'] / 1000:.3f} km"
    )


    print(
        "AI 미지원 거리:",
        f"{result['ai_unsupported_distance_m'] / 1000:.3f} km"
    )


    print(
        "거리 기준 AI Coverage:",
        f"{result['distance_coverage_pct']:.2f}%"
    )


    # ========================================================
    # 지원 LINK
    # ========================================================

    print()
    print(
        "AI 지원 LINK 목록:"
    )


    if result[
        "supported_links"
    ]:

        for item in result[
            "supported_links"
        ]:

            print(

                "  ✓",

                item[
                    "link_id"
                ],

                "|",

                item[
                    "road_name"
                ],

                "|",

                f"{item['length_m']:.1f}m",
            )

    else:

        print(
            "  없음"
        )


    # ========================================================
    # 미지원 LINK
    # ========================================================

    print()
    print(
        "AI 미지원 LINK 목록:"
    )


    if result[
        "unsupported_links"
    ]:

        for item in result[
            "unsupported_links"
        ]:

            print(

                "  ✗",

                item[
                    "link_id"
                ],

                "|",

                item[
                    "road_name"
                ],

                "|",

                f"{item['length_m']:.1f}m",
            )

    else:

        print(
            "  없음"
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
        "FLOW Route × LightGBM AI Coverage 검사"
    )

    print(
        "========================================"
    )


    # ========================================================
    # AI 지원 LINK 읽기
    # ========================================================

    supported_links = (
        load_supported_links()
    )


    print()
    print(
        "AI supported_links.csv LINK 수:",
        len(
            supported_links
        ),
    )


    # ========================================================
    # 예상 AI LINK 수 검증
    # ========================================================

    if len(
        supported_links
    ) != 355:

        print()
        print(
            "주의:"
        )

        print(
            "현재 AI supported LINK 수가 "
            "355개가 아닙니다."
        )

        print(
            "실제 수:",
            len(
                supported_links
            ),
        )


    results = {}


    # ========================================================
    # Route A / B / C 분석
    # ========================================================

    for (
        route_name,
        route_file,
    ) in ROUTE_FILES.items():

        result = (
            analyze_route(

                route_name=
                    route_name,

                route_file=
                    route_file,

                supported_links=
                    supported_links,
            )
        )


        results[
            route_name
        ] = result


        print_route_result(
            result
        )


    # ========================================================
    # 전체 Summary
    # ========================================================

    print()
    print(
        "========================================"
    )

    print(
        "A/B/C Coverage 요약"
    )

    print(
        "========================================"
    )


    print()

    print(
        "Route | Total | AI | LINK % | Distance %"
    )

    print(
        "----------------------------------------"
    )


    for route_name in [
        "A",
        "B",
        "C",
    ]:

        result = results[
            route_name
        ]


        print(

            f"{route_name:>5} | "

            f"{result['total_link_count']:>5} | "

            f"{result['ai_supported_link_count']:>2} | "

            f"{result['link_coverage_pct']:>6.2f}% | "

            f"{result['distance_coverage_pct']:>9.2f}%"
        )


    # ========================================================
    # 결과 JSON
    # ========================================================

    output = {

        "ai_model": {

            "role":
                "baseline_future_traffic",

            "model_version":
                "integration_demo_01",

            "supported_link_count":
                len(
                    supported_links
                ),

            "validation_status":
                "integration_demo_not_final",

            "note":
                (
                    "Coverage only. "
                    "No Traffic Response or "
                    "Synthetic demand applied."
                ),
        },


        "routes":
            results,
    }


    OUTPUT_FILE.parent.mkdir(
        parents=True,
        exist_ok=True,
    )


    with open(
        OUTPUT_FILE,
        "w",
        encoding="utf-8",
    ) as file:

        json.dump(

            output,

            file,

            ensure_ascii=False,

            indent=2,
        )


    print()
    print(
        "========================================"
    )

    print(
        "Coverage 검사 완료"
    )

    print(
        "========================================"
    )


    print(
        "결과 저장:"
    )

    print(
        OUTPUT_FILE
    )


if __name__ == "__main__":

    main()