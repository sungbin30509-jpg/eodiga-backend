import json
import os
from datetime import datetime


# ============================================================
# FLOW 표준 Route JSON 생성
# ============================================================

def build_route_json(
    route_id,
    candidate_id,
    origin,
    destination,
    tmap_route
):

    # --------------------------------------------------------
    # 전체 경로 geometry
    # TMAP route_path:
    #
    # {
    #     "longitude": 127.xxx,
    #     "latitude": 37.xxx
    # }
    #
    # ↓ GeoJSON 형태
    #
    # [경도, 위도]
    # --------------------------------------------------------

    coordinates = []

    for point in tmap_route.get(
        "route_path",
        []
    ):

        coordinates.append(
            [
                point["longitude"],
                point["latitude"]
            ]
        )


    # ========================================================
    # Segment 정리
    # ========================================================

    segments = []

    road_segments = tmap_route.get(
        "road_segments",
        []
    )


    for index, segment in enumerate(
        road_segments
    ):

        segment_data = {

            # FLOW 내부 segment 번호
            "segment_index": index,

            # 도로명
            "road_name": segment.get(
                "name",
                ""
            ),

            # 구간 거리
            "distance_m": segment.get(
                "distance",
                0
            ),

            # 구간 통과시간
            "duration_sec": segment.get(
                "time",
                0
            ),

            # TMAP 교통정보
            "traffic": segment.get(
                "traffic",
                None
            ),

            # =================================================
            # 향후 국가표준 link_id를 여기에 채움
            # =================================================

            "link_ids": []
        }


        segments.append(
            segment_data
        )


    # ========================================================
    # 최종 Route JSON
    # ========================================================

    route_json = {

        # ----------------------------------------------------
        # 기본 정보
        # ----------------------------------------------------

        "route_id": route_id,

        "candidate_id": candidate_id,

        "source": "TMAP",

        "created_at": (
            datetime.now()
            .astimezone()
            .isoformat()
        ),


        # ----------------------------------------------------
        # 출발지
        # ----------------------------------------------------

        "origin": {

            "name": origin.get(
                "name",
                ""
            ),

            "latitude": origin[
                "latitude"
            ],

            "longitude": origin[
                "longitude"
            ]
        },


        # ----------------------------------------------------
        # 목적지
        # ----------------------------------------------------

        "destination": {

            "name": destination.get(
                "name",
                ""
            ),

            "address": destination.get(
                "address",
                ""
            ),

            "latitude": destination[
                "latitude"
            ],

            "longitude": destination[
                "longitude"
            ]
        },


        # ----------------------------------------------------
        # 경로 요약
        # ----------------------------------------------------

        "summary": {

            "distance_m": int(

                tmap_route.get(
                    "distance_km",
                    0
                ) * 1000

            ),

            "duration_sec": int(

                tmap_route.get(
                    "time_min",
                    0
                ) * 60

            ),

            "toll_fare": tmap_route.get(
                "total_fare",
                0
            ),

            "taxi_fare": tmap_route.get(
                "taxi_fare",
                0
            )
        },


        # ----------------------------------------------------
        # 전체 경로 geometry
        # ----------------------------------------------------

        "geometry": {

            "type": "LineString",

            "coordinates": coordinates
        },


        # ----------------------------------------------------
        # TMAP 도로 Segment
        # ----------------------------------------------------

        "segments": segments,


        # ----------------------------------------------------
        # 국가표준 link_id 매핑 결과
        #
        # 다음 단계에서 사용
        # ----------------------------------------------------

        "link_mapping": {

            "status": "not_mapped",

            "matched_link_ids": [],

            "coverage_ratio": 0.0
        }
    }


    return route_json



# ============================================================
# JSON 파일 저장
# ============================================================

def save_route_json(
    route_json,
    output_path
):

    # --------------------------------------------------------
    # 폴더가 없으면 자동 생성
    # --------------------------------------------------------

    directory = os.path.dirname(
        output_path
    )


    if directory:

        os.makedirs(
            directory,
            exist_ok=True
        )


    # --------------------------------------------------------
    # JSON 저장
    # --------------------------------------------------------

    with open(
        output_path,
        "w",
        encoding="utf-8"
    ) as file:

        json.dump(

            route_json,

            file,

            ensure_ascii=False,

            indent=2
        )


    print()
    print(
        "======================================"
    )

    print(
        "FLOW Route JSON 저장 완료"
    )

    print(
        "======================================"
    )

    print(
        "route_id:",
        route_json["route_id"]
    )

    print(
        "저장 위치:",
        output_path
    )

    print(
        "경로 좌표 개수:",
        len(
            route_json[
                "geometry"
            ][
                "coordinates"
            ]
        )
    )

    print(
        "Segment 개수:",
        len(
            route_json[
                "segments"
            ]
        )
    )