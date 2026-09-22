from pathlib import Path
import argparse
import csv
import json
import time
import traceback

from backend.services.route_pipeline import (
    run_route_pipeline,
)


# ============================================================
# FLOW:MATE
# Synthetic Unique OD Batch Route Pipeline
#
# 핵심
# ------------------------------------------------------------
# 1. 10,000명을 직접 Route 처리하지 않음
# 2. 600개 Unique OD만 처리
# 3. OD 하나 실패해도 다음 OD 계속 진행
# 4. 기존 성공 결과 자동 재사용
# 5. 이전 Batch의 잘못된 성공 판정도 자동 재검사
# ============================================================


# ============================================================
# 1. 프로젝트 경로
# ============================================================

ROOT = (
    Path(__file__)
    .resolve()
    .parents[2]
)


OD_FILE = (
    ROOT
    / "data"
    / "generated"
    / "resolved_unique_od.csv"
)


LOCATION_FILE = (
    ROOT
    / "data"
    / "master"
    / "resolved_location_master.csv"
)


OUTPUT_DIR = (
    ROOT
    / "data"
    / "routes"
    / "od_pipeline"
)


SUMMARY_FILE = (
    OUTPUT_DIR
    / "batch_summary.json"
)


OUTPUT_DIR.mkdir(
    parents=True,
    exist_ok=True,
)


# ============================================================
# 2. Region Hint
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
# 3. 문자열 정리
# ============================================================

def clean_text(value):

    if value is None:
        return ""

    return str(value).strip()


# ============================================================
# 4. CSV 읽기
# ============================================================

def load_csv(path):

    if not path.exists():

        raise FileNotFoundError(
            f"파일을 찾을 수 없습니다.\n{path}"
        )


    try:

        with open(
            path,
            "r",
            encoding="utf-8-sig",
            newline="",
        ) as file:

            return list(
                csv.DictReader(file)
            )


    except UnicodeDecodeError:

        with open(
            path,
            "r",
            encoding="cp949",
            newline="",
        ) as file:

            return list(
                csv.DictReader(file)
            )


# ============================================================
# 5. JSON 읽기
# ============================================================

def load_json(path):

    if not path.exists():
        return None


    try:

        with open(
            path,
            "r",
            encoding="utf-8",
        ) as file:

            return json.load(file)


    except Exception:

        return None


# ============================================================
# 6. JSON 저장
# ============================================================

def save_json(
    path,
    data,
):

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
            default=str,
        )


# ============================================================
# 7. Location Lookup
# ============================================================

def build_location_lookup():

    rows = load_csv(
        LOCATION_FILE
    )


    lookup = {}


    for row in rows:

        location_id = clean_text(
            row.get(
                "location_id"
            )
        )


        if not location_id:
            continue


        search_query = clean_text(
            row.get(
                "search_query"
            )
        )


        resolved_name = clean_text(
            row.get(
                "resolved_name"
            )
        )


        input_name = clean_text(
            row.get(
                "input_name"
            )
        )


        region = clean_text(
            row.get(
                "region"
            )
        )


        # 실제 TMAP Resolve에 성공했던 검색어를
        # 최우선으로 재사용
        route_query = (
            search_query
            or resolved_name
            or input_name
        )


        lookup[
            location_id
        ] = {

            "route_query":
                route_query,

            "input_name":
                input_name,

            "resolved_name":
                resolved_name,

            "region":
                region,

            "region_hint":
                REGION_HINT_MAP.get(
                    region
                ),

        }


    return lookup


# ============================================================
# 8. 특정 Key의 값을 전부 재귀적으로 찾기
#
# 이전 버전처럼 첫 status 하나만 찾지 않는다.
# ============================================================

def find_all_values_by_key(
    data,
    target_key,
):

    found_values = []


    if isinstance(
        data,
        dict,
    ):

        for key, value in data.items():

            if key == target_key:

                found_values.append(
                    value
                )


            found_values.extend(

                find_all_values_by_key(
                    value,
                    target_key,
                )

            )


    elif isinstance(
        data,
        list,
    ):

        for item in data:

            found_values.extend(

                find_all_values_by_key(
                    item,
                    target_key,
                )

            )


    return found_values


# ============================================================
# 9. 숫자 변환
# ============================================================

def to_int(value):

    try:

        return int(
            value
        )

    except (
        TypeError,
        ValueError,
    ):

        return None


# ============================================================
# 10. Pipeline 실제 성공 여부 판정
#
# 우선순위:
#
# 1. pipeline_status == ok
# 2. usable_candidate_count > 0
# 3. mapping_success_count > 0
# 4. usable_candidate_ids가 비어 있지 않음
# 5. 최소 하나의 status == mapped
#
# 즉 A/B/C 중 하나 이상 사용할 수 있으면
# OD 자체는 성공으로 본다.
# ============================================================

def assess_pipeline_result(
    pipeline_result,
):

    if not isinstance(
        pipeline_result,
        dict,
    ):

        return {

            "success":
                False,

            "reason":
                "pipeline_result가 dict가 아닙니다.",

            "detected_pipeline_status":
                None,

            "usable_candidate_count":
                0,

        }


    # ========================================================
    # 1. pipeline_status
    # ========================================================

    pipeline_status_values = (

        find_all_values_by_key(

            pipeline_result,

            "pipeline_status",

        )

    )


    normalized_pipeline_status = [

        clean_text(
            value
        ).lower()

        for value
        in pipeline_status_values

    ]


    for status in normalized_pipeline_status:

        if status in {

            "ok",
            "success",
            "completed",

        }:

            return {

                "success":
                    True,

                "reason":
                    (
                        "pipeline_status="
                        f"{status}"
                    ),

                "detected_pipeline_status":
                    status,

                "usable_candidate_count":
                    None,

            }


    # ========================================================
    # 2. usable_candidate_count
    # ========================================================

    usable_counts = (

        find_all_values_by_key(

            pipeline_result,

            "usable_candidate_count",

        )

    )


    for value in usable_counts:

        number = to_int(
            value
        )


        if (
            number is not None
            and
            number > 0
        ):

            return {

                "success":
                    True,

                "reason":
                    (
                        "usable_candidate_count="
                        f"{number}"
                    ),

                "detected_pipeline_status":
                    None,

                "usable_candidate_count":
                    number,

            }


    # ========================================================
    # 3. mapping_success_count
    # ========================================================

    mapping_success_counts = (

        find_all_values_by_key(

            pipeline_result,

            "mapping_success_count",

        )

    )


    for value in mapping_success_counts:

        number = to_int(
            value
        )


        if (
            number is not None
            and
            number > 0
        ):

            return {

                "success":
                    True,

                "reason":
                    (
                        "mapping_success_count="
                        f"{number}"
                    ),

                "detected_pipeline_status":
                    None,

                "usable_candidate_count":
                    number,

            }


    # ========================================================
    # 4. usable_candidate_ids
    # ========================================================

    usable_candidate_ids_values = (

        find_all_values_by_key(

            pipeline_result,

            "usable_candidate_ids",

        )

    )


    for value in usable_candidate_ids_values:

        if (
            isinstance(
                value,
                list,
            )
            and
            len(
                value
            )
            > 0
        ):

            return {

                "success":
                    True,

                "reason":
                    (
                        "usable_candidate_ids="
                        f"{value}"
                    ),

                "detected_pipeline_status":
                    None,

                "usable_candidate_count":
                    len(
                        value
                    ),

            }


    # ========================================================
    # 5. status == mapped
    #
    # 마지막 안전망
    # ========================================================

    all_status_values = (

        find_all_values_by_key(

            pipeline_result,

            "status",

        )

    )


    mapped_count = 0


    for value in all_status_values:

        status = (
            clean_text(
                value
            )
            .lower()
        )


        if status == "mapped":

            mapped_count += 1


    if mapped_count > 0:

        return {

            "success":
                True,

            "reason":
                (
                    "mapped 후보 발견="
                    f"{mapped_count}"
                ),

            "detected_pipeline_status":
                None,

            "usable_candidate_count":
                mapped_count,

        }


    # ========================================================
    # 사용할 수 있는 후보가 없음
    # ========================================================

    return {

        "success":
            False,

        "reason":
            "사용 가능한 Route 후보를 찾지 못했습니다.",

        "detected_pipeline_status":
            (
                normalized_pipeline_status[
                    0
                ]

                if normalized_pipeline_status

                else None
            ),

        "usable_candidate_count":
            0,

    }


# ============================================================
# 11. 기존 Batch 결과 재판정
#
# API를 다시 호출하지 않는다.
# ============================================================

def recheck_existing_result(
    output_file,
):

    existing = load_json(
        output_file
    )


    if not existing:

        return None


    pipeline_result = (
        existing.get(
            "pipeline_result"
        )
    )


    if not isinstance(
        pipeline_result,
        dict,
    ):

        return None


    assessment = (
        assess_pipeline_result(
            pipeline_result
        )
    )


    existing[
        "pipeline_assessment"
    ] = assessment


    if assessment[
        "success"
    ]:

        existing[
            "batch_status"
        ] = "success"

    else:

        existing[
            "batch_status"
        ] = "pipeline_non_ok"


    save_json(
        output_file,
        existing,
    )


    return existing


# ============================================================
# 12. OD 하나 실제 처리
# ============================================================

def process_od(
    od,
    location_lookup,
):

    od_id = clean_text(
        od.get(
            "od_id"
        )
    )


    origin_location_id = clean_text(
        od.get(
            "origin_location_id"
        )
    )


    destination_location_id = clean_text(
        od.get(
            "destination_location_id"
        )
    )


    # ========================================================
    # Location 확인
    # ========================================================

    if (
        origin_location_id
        not in location_lookup
    ):

        raise ValueError(

            f"{od_id}: "
            f"출발지 {origin_location_id}를 "
            "Location Master에서 찾을 수 없습니다."

        )


    if (
        destination_location_id
        not in location_lookup
    ):

        raise ValueError(

            f"{od_id}: "
            f"목적지 {destination_location_id}를 "
            "Location Master에서 찾을 수 없습니다."

        )


    origin = (
        location_lookup[
            origin_location_id
        ]
    )


    destination = (
        location_lookup[
            destination_location_id
        ]
    )


    origin_query = (
        origin[
            "route_query"
        ]
    )


    destination_query = (
        destination[
            "route_query"
        ]
    )


    origin_region_hint = (
        origin[
            "region_hint"
        ]
    )


    destination_region_hint = (
        destination[
            "region_hint"
        ]
    )


    print()

    print(
        "========================================"
    )

    print(
        od_id
    )

    print(
        "========================================"
    )


    print(

        "출발:",

        origin_query,

        f"({origin_location_id})",

    )


    print(

        "도착:",

        destination_query,

        f"({destination_location_id})",

    )


    print(

        "Synthetic 사용자:",

        od.get(
            "user_count"
        ),

    )


    # ========================================================
    # Universal Route Pipeline
    # ========================================================

    pipeline_result = (

        run_route_pipeline(

            origin_query,

            destination_query,

            origin_region_hint=(
                origin_region_hint
            ),

            destination_region_hint=(
                destination_region_hint
            ),

        )

    )


    # ========================================================
    # 성공 여부 판정
    # ========================================================

    assessment = (

        assess_pipeline_result(
            pipeline_result
        )

    )


    if assessment[
        "success"
    ]:

        batch_status = (
            "success"
        )

    else:

        batch_status = (
            "pipeline_non_ok"
        )


    return {

        "batch_status":
            batch_status,

        "od_id":
            od_id,

        "user_count":
            int(
                od.get(
                    "user_count",
                    0,
                )
            ),

        "origin": {

            "location_id":
                origin_location_id,

            "input_name":
                clean_text(
                    od.get(
                        "origin_name"
                    )
                ),

            "route_query":
                origin_query,

            "region_hint":
                origin_region_hint,

            "lat":
                od.get(
                    "origin_lat"
                ),

            "lon":
                od.get(
                    "origin_lon"
                ),

        },

        "destination": {

            "location_id":
                destination_location_id,

            "input_name":
                clean_text(
                    od.get(
                        "destination_name"
                    )
                ),

            "route_query":
                destination_query,

            "region_hint":
                destination_region_hint,

            "region":
                clean_text(
                    od.get(
                        "destination_region"
                    )
                ),

            "lat":
                od.get(
                    "destination_lat"
                ),

            "lon":
                od.get(
                    "destination_lon"
                ),

        },

        "pipeline_assessment":
            assessment,

        "pipeline_result":
            pipeline_result,

    }


# ============================================================
# 13. Batch
# ============================================================

def run_batch(
    limit=None,
    force=False,
    sleep_seconds=0.15,
):

    print()

    print(
        "========================================"
    )

    print(
        "FLOW:MATE Unique OD Batch Pipeline"
    )

    print(
        "========================================"
    )


    od_rows = load_csv(
        OD_FILE
    )


    location_lookup = (
        build_location_lookup()
    )


    # ========================================================
    # Limit
    # ========================================================

    if (
        limit is not None
        and
        limit > 0
    ):

        target_rows = (
            od_rows[
                :limit
            ]
        )

    else:

        target_rows = (
            od_rows
        )


    print(
        "전체 Unique OD:",
        len(
            od_rows
        ),
    )


    print(
        "Location:",
        len(
            location_lookup
        ),
    )


    print(
        "이번 실행 대상:",
        len(
            target_rows
        ),
    )


    print(
        "Force:",
        force,
    )


    # ========================================================
    # 통계
    # ========================================================

    api_processed_count = 0

    rechecked_count = 0

    success_count = 0

    failed_count = 0

    skipped_success_count = 0


    failed_od_ids = []


    started_at = (
        time.time()
    )


    # ========================================================
    # 반복
    # ========================================================

    for index, od in enumerate(
        target_rows,
        start=1,
    ):

        od_id = clean_text(
            od.get(
                "od_id"
            )
        )


        output_file = (
            OUTPUT_DIR
            /
            f"{od_id}.json"
        )


        print()

        print(
            "########################################"
        )

        print(

            f"Batch {index}/{len(target_rows)}",

            "|",

            od_id,

        )

        print(
            "########################################"
        )


        # ====================================================
        # 기존 결과가 있으면 먼저 재판정
        #
        # force가 없으면 API 재호출하지 않는다.
        # ====================================================

        if (
            output_file.exists()
            and
            not force
        ):

            existing = (
                recheck_existing_result(
                    output_file
                )
            )


            if existing:

                rechecked_count += 1


                if (
                    existing.get(
                        "batch_status"
                    )
                    ==
                    "success"
                ):

                    success_count += 1


                    print(
                        "✅ 기존 결과 재판정 성공"
                    )


                    assessment = (
                        existing.get(
                            "pipeline_assessment",
                            {},
                        )
                    )


                    print(

                        "판정 근거:",

                        assessment.get(
                            "reason"
                        ),

                    )


                    continue


                else:

                    print(
                        "⚠️ 기존 결과 재판정 실패"
                    )


                    print(
                        "실제 Pipeline을 다시 실행합니다."
                    )


            else:

                existing_raw = (
                    load_json(
                        output_file
                    )
                )


                if (
                    existing_raw
                    and
                    existing_raw.get(
                        "batch_status"
                    )
                    ==
                    "success"
                ):

                    skipped_success_count += 1

                    success_count += 1


                    print(
                        "⏭️ 기존 성공 결과 Skip"
                    )


                    continue


        # ====================================================
        # 실제 Pipeline 실행
        # ====================================================

        try:

            result = (
                process_od(

                    od,

                    location_lookup,

                )
            )


            save_json(
                output_file,
                result,
            )


            api_processed_count += 1


            if (
                result[
                    "batch_status"
                ]
                ==
                "success"
            ):

                success_count += 1


                print()

                print(
                    f"✅ {od_id} 성공"
                )


                print(

                    "판정 근거:",

                    result[
                        "pipeline_assessment"
                    ][
                        "reason"
                    ],

                )


            else:

                failed_count += 1

                failed_od_ids.append(
                    od_id
                )


                print()

                print(
                    f"⚠️ {od_id} 실패"
                )


                print(

                    "판정 근거:",

                    result[
                        "pipeline_assessment"
                    ][
                        "reason"
                    ],

                )


        except Exception as error:

            api_processed_count += 1

            failed_count += 1


            failed_od_ids.append(
                od_id
            )


            failure_output = {

                "batch_status":
                    "failed",

                "od_id":
                    od_id,

                "user_count":
                    int(
                        od.get(
                            "user_count",
                            0,
                        )
                    ),

                "error_type":
                    type(
                        error
                    ).__name__,

                "error_message":
                    str(
                        error
                    ),

                "traceback":
                    traceback.format_exc(),

            }


            save_json(
                output_file,
                failure_output,
            )


            print()

            print(
                f"❌ {od_id} 예외 발생"
            )


            print(
                "오류 종류:",
                type(
                    error
                ).__name__,
            )


            print(
                "오류 내용:",
                error,
            )


            print(
                "다음 OD 처리를 계속합니다."
            )


        if sleep_seconds > 0:

            time.sleep(
                sleep_seconds
            )


    # ========================================================
    # Summary
    # ========================================================

    elapsed_seconds = (
        time.time()
        -
        started_at
    )


    summary = {

        "total_unique_od":
            len(
                od_rows
            ),

        "selected_od_count":
            len(
                target_rows
            ),

        "api_processed_count":
            api_processed_count,

        "rechecked_existing_count":
            rechecked_count,

        "skipped_existing_success_count":
            skipped_success_count,

        "success_count":
            success_count,

        "failed_count":
            failed_count,

        "failed_od_ids":
            failed_od_ids,

        "elapsed_seconds":
            round(
                elapsed_seconds,
                2,
            ),

        "output_directory":
            str(
                OUTPUT_DIR
            ),

    }


    save_json(
        SUMMARY_FILE,
        summary,
    )


    # ========================================================
    # 출력
    # ========================================================

    print()

    print(
        "========================================"
    )

    print(
        "Batch 결과"
    )

    print(
        "========================================"
    )


    print(
        "전체 Unique OD:",
        len(
            od_rows
        ),
    )


    print(
        "이번 실행 대상:",
        len(
            target_rows
        ),
    )


    print(
        "API 신규 처리:",
        api_processed_count,
    )


    print(
        "기존 결과 재판정:",
        rechecked_count,
    )


    print(
        "기존 성공 Skip:",
        skipped_success_count,
    )


    print(
        "성공:",
        success_count,
    )


    print(
        "실패:",
        failed_count,
    )


    if failed_od_ids:

        print()

        print(
            "실패 OD:"
        )


        for od_id in failed_od_ids:

            print(
                "-",
                od_id,
            )


    print()

    print(
        "소요 시간:",
        round(
            elapsed_seconds,
            1,
        ),
        "초",
    )


    print()

    print(
        "결과 폴더:"
    )


    print(
        OUTPUT_DIR
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
        "Batch 실행 완료"
    )

    print(
        "========================================"
    )


    return summary


# ============================================================
# 14. CLI
# ============================================================

def main():

    parser = argparse.ArgumentParser(

        description=(
            "FLOW:MATE Unique OD "
            "Batch Route Pipeline"
        )

    )


    parser.add_argument(

        "--limit",

        type=int,

        default=None,

        help=(
            "처리할 OD 개수. "
            "예: --limit 5"
        ),

    )


    parser.add_argument(

        "--force",

        action="store_true",

        help=(
            "기존 결과가 있어도 "
            "TMAP/Route Pipeline을 다시 실행"
        ),

    )


    parser.add_argument(

        "--sleep",

        type=float,

        default=0.15,

        help=(
            "OD 사이 대기시간(초)"
        ),

    )


    args = (
        parser.parse_args()
    )


    run_batch(

        limit=args.limit,

        force=args.force,

        sleep_seconds=args.sleep,

    )


# ============================================================
# 15. 직접 실행
# ============================================================

if __name__ == "__main__":

    main()