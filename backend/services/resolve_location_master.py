from pathlib import Path
import json
import time

import pandas as pd

from backend.services.location_service import (
    resolve_location,
)


# ============================================================
# FLOW:MATE
# Location Master Resolver
#
# 역할
# ------------------------------------------------------------
# Synthetic Location Master
#        ↓
# TMAP POI 검색
#        ↓
# 지역 검증
#        ↓
# 실제 좌표 확보
#        ↓
# resolved_location_master.csv
#
#
# 중요
# ------------------------------------------------------------
# - 원본 location_master.csv는 수정하지 않는다.
# - TMAP 검색용 별칭은 이 파일에서 관리한다.
# - 검색 결과 주소가 예상 지역과 다르면 실패 처리한다.
# - 특정 장소는 여러 검색어를 순서대로 시도한다.
# - 경로당/상가처럼 대표 POI로 부적절한 결과도 필터링한다.
# ============================================================


# ============================================================
# 1. 프로젝트 경로
# ============================================================

ROOT = (
    Path(__file__)
    .resolve()
    .parents[2]
)


INPUT_FILE = (
    ROOT
    / "data"
    / "master"
    / "location_master.csv"
)


OUTPUT_DIR = (
    ROOT
    / "data"
    / "master"
)


RESOLVED_FILE = (
    OUTPUT_DIR
    / "resolved_location_master.csv"
)


UNRESOLVED_FILE = (
    OUTPUT_DIR
    / "unresolved_location_master.csv"
)


SUMMARY_FILE = (
    OUTPUT_DIR
    / "location_resolution_summary.json"
)


OUTPUT_DIR.mkdir(
    parents=True,
    exist_ok=True,
)


# ============================================================
# 2. Synthetic region
#    →
#    TMAP 검색 Region Hint
# ============================================================

REGION_HINT_MAP = {

    "seongnam":
        "성남시",

    "seoul":
        "서울특별시",

    "suwon":
        "수원시",

    "yongin":
        "용인시",

    "gwangju":
        "광주시",

    "hanam":
        "하남시",

}


# ============================================================
# 3. 검색 결과 주소 검증용 키워드
#
# 예:
#
# HOME_017 파크타운아파트
#
# 잘못된 결과:
# 서울 용산구 ...
#
# 예상:
# 경기 성남시 ...
#
# → 자동 실패 처리
# ============================================================

REGION_ADDRESS_KEYWORDS = {

    "seongnam":
        "성남시",

    "seoul":
        "서울",

    "suwon":
        "수원시",

    "yongin":
        "용인시",

    "gwangju":
        "광주시",

    "hanam":
        "하남시",

}


# ============================================================
# 4. TMAP 검색어 후보
#
# 기본적으로는 location_master.csv의 name을 사용한다.
#
# 아래 장소들만 TMAP 검색이 어렵거나
# 대표 POI가 잘못 잡혔기 때문에
# 별도 검색어 후보를 사용한다.
# ============================================================

SEARCH_QUERY_CANDIDATES = {

    # --------------------------------------------------------
    # 기존 검색:
    # NHN Play Museum
    #
    # 결과:
    # HTTP 204
    # --------------------------------------------------------

    "ORG_005": [

        "NHN 플레이뮤지엄",

        "NHN 판교",

        "NHN",

    ],


    # --------------------------------------------------------
    # 기존 검색:
    # 위메이드 판교 사옥
    #
    # 결과:
    # HTTP 204
    # --------------------------------------------------------

    "ORG_007": [

        "위메이드타워",

        "위메이드 판교타워",

        "위메이드",

    ],


    # --------------------------------------------------------
    # 기존 검색:
    # 백현마을5단지(주공)
    #
    # 결과:
    # HTTP 204
    # --------------------------------------------------------

    "HOME_006": [

        "백현마을5단지아파트",

        "백현마을5단지",

        "분당 백현마을5단지",

    ],


    # --------------------------------------------------------
    # 기존 검색:
    # 파크타운아파트
    #
    # 잘못된 결과:
    # 서울 용산구
    # --------------------------------------------------------

    "HOME_017": [

        "분당 파크타운아파트",

        "분당 파크타운",

        "성남 파크타운아파트",

    ],


    # --------------------------------------------------------
    # 기존 검색:
    # 성남 센트럴타운
    #
    # 결과:
    # 성남센트럴타운경로당
    #
    # 주소는 맞지만 대표 POI가 아님.
    # --------------------------------------------------------

    "HOME_021": [

        "성남센트럴타운아파트",

        "센트럴타운아파트 여수동",

        "성남 센트럴타운",

    ],


    # --------------------------------------------------------
    # 기존 검색:
    # 성남단대푸르지오
    #
    # 결과:
    # 성남단대푸르지오아파트상가
    # --------------------------------------------------------

    "HOME_022": [

        "성남단대푸르지오아파트",

        "단대푸르지오아파트",

        "성남단대푸르지오",

    ],

}


# ============================================================
# 5. 특정 장소에서 사용하지 않을 POI 이름
#
# 주소가 맞더라도
# 아파트 자체가 아니라 경로당/상가 등이 검색되는 경우
# 다음 검색어를 시도한다.
# ============================================================

REJECTED_NAME_KEYWORDS = {

    "HOME_021": [

        "경로당",

    ],

    "HOME_022": [

        "상가",

    ],

}


# ============================================================
# 6. 문자열 정리
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
# 7. Location Master 읽기
# ============================================================

def load_location_master():

    if not INPUT_FILE.exists():

        raise FileNotFoundError(

            "location_master.csv를 찾을 수 없습니다.\n"
            f"{INPUT_FILE}"

        )


    # ========================================================
    # UTF-8-SIG 우선
    # ========================================================

    try:

        df = pd.read_csv(

            INPUT_FILE,

            dtype=str,

            encoding="utf-8-sig",

        )


    except UnicodeDecodeError:

        df = pd.read_csv(

            INPUT_FILE,

            dtype=str,

            encoding="cp949",

        )


    # ========================================================
    # 빈 파일 검사
    # ========================================================

    if df.empty:

        raise ValueError(
            "location_master.csv가 비어 있습니다."
        )


    # ========================================================
    # 컬럼명 공백 제거
    # ========================================================

    df.columns = [

        clean_text(
            column
        )

        for column
        in df.columns

    ]


    # ========================================================
    # 필수 컬럼
    # ========================================================

    required_columns = [

        "location_id",

        "name",

        "location_type",

        "region",

    ]


    missing_columns = [

        column

        for column
        in required_columns

        if column
        not in df.columns

    ]


    if missing_columns:

        raise ValueError(

            "Location Master 필수 컬럼이 없습니다.\n"
            f"{missing_columns}\n\n"
            f"현재 컬럼:\n"
            f"{df.columns.tolist()}"

        )


    # ========================================================
    # 문자열 정리
    # ========================================================

    for column in required_columns:

        df[column] = (

            df[column]
            .apply(
                clean_text
            )

        )


    # ========================================================
    # location_id 중복 검사
    # ========================================================

    duplicated = (

        df[
            "location_id"
        ]

        .duplicated(
            keep=False
        )

    )


    if duplicated.any():

        duplicated_ids = (

            df.loc[
                duplicated,
                "location_id"
            ]

            .tolist()

        )


        raise ValueError(

            "location_master.csv에 "
            "중복 location_id가 있습니다.\n"
            f"{duplicated_ids}"

        )


    return df


# ============================================================
# 8. Region Hint 결정
# ============================================================

def get_region_hint(
    row,
):

    location_id = clean_text(
        row[
            "location_id"
        ]
    )


    region = clean_text(
        row[
            "region"
        ]
    )


    # ========================================================
    # ORG는 판교 업무지역
    #
    # 모두 성남시로 검색
    # ========================================================

    if location_id.startswith(
        "ORG_"
    ):

        return "성남시"


    return REGION_HINT_MAP.get(
        region
    )


# ============================================================
# 9. 검색어 후보 생성
# ============================================================

def get_search_queries(
    location_id,
    original_name,
):

    # ========================================================
    # 별도 검색어가 지정된 경우
    # ========================================================

    if (
        location_id
        in SEARCH_QUERY_CANDIDATES
    ):

        queries = list(

            SEARCH_QUERY_CANDIDATES[
                location_id
            ]

        )


        # 원본 검색어도 마지막 후보로 추가
        if (
            original_name
            and
            original_name
            not in queries
        ):

            queries.append(
                original_name
            )


        return queries


    # ========================================================
    # 일반 장소
    # ========================================================

    return [
        original_name
    ]


# ============================================================
# 10. 검색 결과 지역 검증
# ============================================================

def validate_resolved_region(
    region,
    resolved_address,
):

    expected_keyword = (
        REGION_ADDRESS_KEYWORDS.get(
            region
        )
    )


    # region 정보가 정의되지 않은 경우
    # 지역 검증 생략
    if not expected_keyword:

        return (
            True,
            None,
        )


    if (
        expected_keyword
        not in resolved_address
    ):

        return (

            False,

            (
                "검색 결과 지역 불일치: "
                f"예상={expected_keyword}, "
                f"결과={resolved_address}"
            ),

        )


    return (
        True,
        None,
    )


# ============================================================
# 11. 대표 POI 적합성 검사
# ============================================================

def validate_resolved_name(
    location_id,
    resolved_name,
):

    rejected_keywords = (

        REJECTED_NAME_KEYWORDS.get(
            location_id,
            [],
        )

    )


    for keyword in rejected_keywords:

        if (
            keyword
            in resolved_name
        ):

            return (

                False,

                (
                    "대표 POI 부적합: "
                    f"resolved_name={resolved_name}, "
                    f"금지 키워드={keyword}"
                ),

            )


    return (
        True,
        None,
    )


# ============================================================
# 12. 장소 1개 Resolve
# ============================================================

def resolve_master_location(
    row,
):

    location_id = clean_text(
        row[
            "location_id"
        ]
    )


    original_name = clean_text(
        row[
            "name"
        ]
    )


    location_type = clean_text(
        row[
            "location_type"
        ]
    )


    region = clean_text(
        row[
            "region"
        ]
    )


    region_hint = (
        get_region_hint(
            row
        )
    )


    search_queries = (
        get_search_queries(

            location_id,

            original_name,

        )
    )


    # ========================================================
    # 실패 이유 기록
    # ========================================================

    attempt_errors = []


    # ========================================================
    # 검색어를 순서대로 시도
    # ========================================================

    for search_query in search_queries:

        try:

            result = (
                resolve_location(

                    search_query,

                    region_hint=(
                        region_hint
                    ),

                )
            )


            # =================================================
            # 결과 값 정리
            # =================================================

            resolved_name = clean_text(

                result.get(
                    "name",
                    ""
                )

            )


            resolved_address = clean_text(

                result.get(
                    "address",
                    ""
                )

            )


            lat = result.get(
                "lat"
            )


            lon = result.get(
                "lon"
            )


            # =================================================
            # 좌표 검사
            # =================================================

            if (
                lat is None
                or
                lon is None
            ):

                raise ValueError(
                    "검색 결과에 좌표가 없습니다."
                )


            # =================================================
            # 지역 검사
            # =================================================

            (
                region_valid,
                region_error,
            ) = validate_resolved_region(

                region,

                resolved_address,

            )


            if not region_valid:

                attempt_errors.append(

                    (
                        f"[{search_query}] "
                        f"{region_error}"
                    )

                )

                continue


            # =================================================
            # 대표 POI 이름 검사
            # =================================================

            (
                name_valid,
                name_error,
            ) = validate_resolved_name(

                location_id,

                resolved_name,

            )


            if not name_valid:

                attempt_errors.append(

                    (
                        f"[{search_query}] "
                        f"{name_error}"
                    )

                )

                continue


            # =================================================
            # 정상 검색 성공
            # =================================================

            return {

                "status":
                    "resolved",

                "location_id":
                    location_id,

                # 원본 Synthetic 이름
                "input_name":
                    original_name,

                # 실제 성공한 TMAP 검색어
                "search_query":
                    search_query,

                "location_type":
                    location_type,

                "region":
                    region,

                "region_hint":
                    region_hint
                    or
                    "",

                "resolved_name":
                    resolved_name,

                "resolved_address":
                    resolved_address,

                "lat":
                    lat,

                "lon":
                    lon,

                "poi_id":
                    result.get(
                        "poi_id"
                    ),

                "match_score":
                    result.get(
                        "match_score"
                    ),

                "source":
                    result.get(
                        "source"
                    ),

                "cached":
                    result.get(
                        "cached",
                        False,
                    ),

                "attempt_count":
                    len(
                        attempt_errors
                    )
                    + 1,

                "attempted_queries":
                    " | ".join(
                        search_queries[
                            :len(attempt_errors) + 1
                        ]
                    ),

                "error":
                    "",

            }


        except Exception as error:

            attempt_errors.append(

                (
                    f"[{search_query}] "
                    f"{error}"
                )

            )


        # API 연속 호출 완화
        time.sleep(
            0.05
        )


    # ========================================================
    # 모든 검색어 실패
    # ========================================================

    return {

        "status":
            "failed",

        "location_id":
            location_id,

        "input_name":
            original_name,

        "search_query":
            "",

        "location_type":
            location_type,

        "region":
            region,

        "region_hint":
            region_hint
            or
            "",

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

        "source":
            None,

        "cached":
            False,

        "attempt_count":
            len(
                search_queries
            ),

        "attempted_queries":
            " | ".join(
                search_queries
            ),

        "error":
            " / ".join(
                attempt_errors
            ),

    }


# ============================================================
# 13. 전체 Location Master Resolve
# ============================================================

def resolve_location_master():

    locations = (
        load_location_master()
    )


    results = []


    total = len(
        locations
    )


    print()

    print(
        "========================================"
    )

    print(
        "FLOW:MATE Location Master Resolver"
    )

    print(
        "========================================"
    )


    print(

        "전체 장소:",

        total,

    )


    print()


    # ========================================================
    # 55개 장소 순회
    # ========================================================

    for index, row in (
        locations.iterrows()
    ):

        current = (
            index
            +
            1
        )


        location_id = (
            row[
                "location_id"
            ]
        )


        original_name = (
            row[
                "name"
            ]
        )


        print(

            f"[{current}/{total}]",

            location_id,

            original_name,

            "...",

            end=" ",

            flush=True,

        )


        result = (
            resolve_master_location(
                row
            )
        )


        results.append(
            result
        )


        # ====================================================
        # 성공
        # ====================================================

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

                "|",

                result[
                    "resolved_address"
                ],

                "| query:",

                result[
                    "search_query"
                ],

                "| cached:",

                result[
                    "cached"
                ],

            )


        # ====================================================
        # 실패
        # ====================================================

        else:

            print(
                "❌ FAILED"
            )


            print(

                "    검색 후보:",

                result[
                    "attempted_queries"
                ],

            )


            print(

                "    실패 이유:",

                result[
                    "error"
                ],

            )


        time.sleep(
            0.05
        )


    # ========================================================
    # DataFrame
    # ========================================================

    result_df = (
        pd.DataFrame(
            results
        )
    )


    # ========================================================
    # 성공 / 실패
    # ========================================================

    success_df = (

        result_df[

            result_df[
                "status"
            ]

            ==

            "resolved"

        ]

        .copy()

    )


    failed_df = (

        result_df[

            result_df[
                "status"
            ]

            ==

            "failed"

        ]

        .copy()

    )


    # ========================================================
    # 정렬
    # ========================================================

    success_df = (

        success_df

        .sort_values(
            by="location_id"
        )

        .reset_index(
            drop=True
        )

    )


    failed_df = (

        failed_df

        .sort_values(
            by="location_id"
        )

        .reset_index(
            drop=True
        )

    )


    # ========================================================
    # CSV 저장
    # ========================================================

    success_df.to_csv(

        RESOLVED_FILE,

        index=False,

        encoding="utf-8-sig",

    )


    failed_df.to_csv(

        UNRESOLVED_FILE,

        index=False,

        encoding="utf-8-sig",

    )


    # ========================================================
    # Summary
    # ========================================================

    failed_location_ids = (

        failed_df[
            "location_id"
        ]
        .tolist()

        if not failed_df.empty

        else []

    )


    summary = {

        "total_location_count":
            total,

        "resolved_count":
            len(
                success_df
            ),

        "failed_count":
            len(
                failed_df
            ),

        "success_rate_percent":
            round(

                (
                    len(
                        success_df
                    )

                    /

                    total

                    *

                    100
                )

                if total > 0

                else 0.0,

                2,

            ),

        "failed_location_ids":
            failed_location_ids,

        "resolved_file":
            str(
                RESOLVED_FILE
            ),

        "unresolved_file":
            str(
                UNRESOLVED_FILE
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
        "Location Resolution 결과"
    )

    print(
        "========================================"
    )


    print(

        "전체 장소:",

        total,

    )


    print(

        "성공:",

        len(
            success_df
        ),

    )


    print(

        "실패:",

        len(
            failed_df
        ),

    )


    print(

        "성공률:",

        summary[
            "success_rate_percent"
        ],

        "%",

    )


    # ========================================================
    # 실패 Location 출력
    # ========================================================

    if failed_location_ids:

        print()

        print(
            "실패 Location:"
        )


        for location_id in (
            failed_location_ids
        ):

            print(
                "-",
                location_id,
            )


    print()

    print(
        "성공 파일:"
    )


    print(
        RESOLVED_FILE
    )


    print()

    print(
        "실패 파일:"
    )


    print(
        UNRESOLVED_FILE
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


    if (
        len(
            failed_df
        )
        ==
        0
    ):

        print(
            "✅ Location Master Resolve 완료"
        )


    else:

        print(

            "⚠️ Location Master Resolve 완료"
            " - 일부 장소 재검토 필요"

        )


    print(
        "========================================"
    )


    return result_df


# ============================================================
# 14. 직접 실행
# ============================================================

if __name__ == "__main__":

    resolve_location_master()