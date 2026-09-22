from pathlib import Path
import shutil
import py_compile


# ============================================================
# Phase 2 Route Engine Traffic Patch
#
# 읽는 파일:
# route_engine_phase2_current.py
#
# 만드는 파일:
# backend/services/route_engine.py
#
# Phase 1은 절대 건드리지 않음.
# ============================================================


ROOT = Path(__file__).resolve().parent

SOURCE = (
    ROOT
    / "route_engine_phase2_current.py"
)

TARGET = (
    ROOT
    / "backend"
    / "services"
    / "route_engine.py"
)

BACKUP = (
    ROOT
    / "backend"
    / "services"
    / "route_engine.before_phase2_traffic.py.bak"
)


# ============================================================
# 1. 파일 확인
# ============================================================

if not SOURCE.exists():
    raise FileNotFoundError(
        f"원본 파일을 찾을 수 없습니다:\n{SOURCE}"
    )


if not TARGET.exists():
    raise FileNotFoundError(
        f"Phase 2 route_engine.py를 찾을 수 없습니다:\n{TARGET}"
    )


print()
print("========================================")
print("Phase 2 Route Engine Traffic Patch")
print("========================================")
print()

print("SOURCE:")
print(SOURCE)

print()
print("TARGET:")
print(TARGET)

print()


# ============================================================
# 2. Phase 2 현재 route_engine 백업
# ============================================================

shutil.copy2(
    TARGET,
    BACKUP,
)

print("기존 Phase 2 route_engine 백업 완료:")
print(BACKUP)
print()


# ============================================================
# 3. 업로드/복사한 검증본 읽기
# ============================================================

text = SOURCE.read_text(
    encoding="utf-8",
)


# ============================================================
# 이미 적용됐는지 검사
# ============================================================

if (
    "def extract_tmap_traffic_segments"
    in text
):

    raise RuntimeError(
        "route_engine_phase2_current.py에 "
        "이미 Traffic 코드가 포함되어 있습니다."
    )


# ============================================================
# 4. TMAP Traffic 추출 함수
# ============================================================

TRAFFIC_FUNCTION = r'''
# ============================================================
# 6-1. TMAP 현재 교통정보 구간 추출
#
# trafficInfo = "Y"일 때
# TMAP 자동차 경로의 LineString geometry에는
#
# traffic = [
#     시작 index,
#     마지막 index,
#     혼잡도,
#     속도
# ]
#
# 가 포함될 수 있다.
#
# congestion_level
#
# 0 = 정보없음
# 1 = 원활
# 2 = 서행
# 3 = 지체
# 4 = 정체
#
# 중요:
# 이것은 현재 시점 TMAP 교통정보이다.
# LightGBM 미래 교통예측 결과가 아니다.
# ============================================================

def extract_tmap_traffic_segments(
    features,
):

    traffic_segments = []

    sequence = 0


    congestion_labels = {

        0:
            "정보없음",

        1:
            "원활",

        2:
            "서행",

        3:
            "지체",

        4:
            "정체",

    }


    for feature in features:

        if not isinstance(
            feature,
            dict,
        ):

            continue


        # ----------------------------------------------------
        # Geometry
        # ----------------------------------------------------

        geometry = (
            feature.get(
                "geometry",
                {},
            )
        )


        if not isinstance(
            geometry,
            dict,
        ):

            continue


        if (
            geometry.get(
                "type"
            )
            !=
            "LineString"
        ):

            continue


        coordinates = (
            geometry.get(
                "coordinates",
                [],
            )
        )


        if (
            not isinstance(
                coordinates,
                list,
            )
            or
            len(
                coordinates
            )
            < 2
        ):

            continue


        # ----------------------------------------------------
        # Properties
        # ----------------------------------------------------

        properties = (
            feature.get(
                "properties",
                {},
            )
        )


        if not isinstance(
            properties,
            dict,
        ):

            properties = {}


        # ----------------------------------------------------
        # TMAP Traffic
        #
        # 공식 자동차 경로응답:
        #
        # geometry.traffic
        #
        # 예:
        #
        # [0, 5, 2, 17]
        #
        # 0   → 시작 coordinate index
        # 5   → 마지막 coordinate index
        # 2   → 서행
        # 17  → 17 km/h
        # ----------------------------------------------------

        traffic = (
            geometry.get(
                "traffic"
            )
        )


        # ----------------------------------------------------
        # API 응답 변형을 고려한 방어적 fallback
        # ----------------------------------------------------

        if traffic is None:

            traffic = (
                feature.get(
                    "traffic"
                )
            )


        if traffic is None:

            traffic = (
                properties.get(
                    "traffic"
                )
            )


        # 문자열 형태가 들어온 경우도 방어적으로 처리
        if isinstance(
            traffic,
            str,
        ):

            try:

                traffic = (
                    json.loads(
                        traffic
                    )
                )

            except (
                json.JSONDecodeError,
                TypeError,
            ):

                traffic = None


        # ----------------------------------------------------
        # Traffic 배열 정규화
        #
        # 일반:
        #
        # [start, end, level, speed]
        #
        # 혹시 중첩:
        #
        # [
        #   [start, end, level, speed],
        #   ...
        # ]
        #
        # 형태가 와도 처리.
        # ----------------------------------------------------

        traffic_items = []


        if isinstance(
            traffic,
            (
                list,
                tuple,
            ),
        ):

            if (
                len(
                    traffic
                )
                >= 4
                and
                not isinstance(
                    traffic[0],
                    (
                        list,
                        tuple,
                    ),
                )
            ):

                traffic_items = [
                    traffic
                ]


            else:

                traffic_items = [

                    item

                    for item
                    in traffic

                    if (
                        isinstance(
                            item,
                            (
                                list,
                                tuple,
                            ),
                        )
                        and
                        len(
                            item
                        )
                        >= 4
                    )

                ]


        # ----------------------------------------------------
        # 교통정보 없는 LineString
        #
        # Geometry 자체는 버리지 않고
        # 정보없음(level=0)으로 Flutter에 전달.
        #
        # 나중에 회색 선으로 표시한다.
        # ----------------------------------------------------

        if not traffic_items:

            traffic_segments.append({

                "sequence":
                    sequence,

                "feature_index":
                    properties.get(
                        "index"
                    ),

                "line_index":
                    properties.get(
                        "lineIndex"
                    ),

                "road_name":
                    properties.get(
                        "name"
                    ),

                "start_index":
                    0,

                "end_index":
                    (
                        len(
                            coordinates
                        )
                        - 1
                    ),

                "congestion_level":
                    0,

                "congestion_label":
                    congestion_labels[
                        0
                    ],

                "speed_kmh":
                    None,

                "geometry":
                    coordinates,

                "coordinate_order":
                    "lon_lat",

                "source":
                    "tmap_current",

            })


            sequence += 1

            continue


        # ----------------------------------------------------
        # Traffic 구간별 처리
        # ----------------------------------------------------

        for item in traffic_items:

            try:

                start_index = int(
                    float(
                        item[0]
                    )
                )


                end_index = int(
                    float(
                        item[1]
                    )
                )


                congestion_level = int(
                    float(
                        item[2]
                    )
                )


                speed_kmh = (

                    float(
                        item[3]
                    )

                    if (
                        item[3]
                        is not None
                    )

                    else None

                )


            except (
                TypeError,
                ValueError,
                IndexError,
            ):

                continue


            # ------------------------------------------------
            # Index 범위 보호
            # ------------------------------------------------

            start_index = max(

                0,

                min(
                    start_index,
                    len(
                        coordinates
                    )
                    - 1,
                ),

            )


            end_index = max(

                0,

                min(
                    end_index,
                    len(
                        coordinates
                    )
                    - 1,
                ),

            )


            # ------------------------------------------------
            # 시작/끝이 뒤집힌 경우
            # ------------------------------------------------

            if (
                end_index
                <
                start_index
            ):

                (
                    start_index,
                    end_index,
                ) = (
                    end_index,
                    start_index,
                )


            # ------------------------------------------------
            # 점 하나만 선택된 경우
            #
            # Polyline을 만들려면 최소 2점 필요
            # ------------------------------------------------

            if (
                end_index
                ==
                start_index
            ):

                if (
                    end_index + 1
                    <
                    len(
                        coordinates
                    )
                ):

                    end_index += 1


                elif (
                    start_index
                    >
                    0
                ):

                    start_index -= 1


            # ------------------------------------------------
            # 해당 교통구간 Geometry
            # ------------------------------------------------

            segment_geometry = (
                coordinates[
                    start_index:
                    end_index + 1
                ]
            )


            if (
                len(
                    segment_geometry
                )
                < 2
            ):

                continue


            # ------------------------------------------------
            # 공식 혼잡도 이외 값 보호
            # ------------------------------------------------

            if (
                congestion_level
                not in {
                    0,
                    1,
                    2,
                    3,
                    4,
                }
            ):

                congestion_level = 0


            # ------------------------------------------------
            # 결과
            # ------------------------------------------------

            traffic_segments.append({

                "sequence":
                    sequence,

                "feature_index":
                    properties.get(
                        "index"
                    ),

                "line_index":
                    properties.get(
                        "lineIndex"
                    ),

                "road_name":
                    properties.get(
                        "name"
                    ),

                "start_index":
                    start_index,

                "end_index":
                    end_index,

                "congestion_level":
                    congestion_level,

                "congestion_label":
                    congestion_labels[
                        congestion_level
                    ],

                "speed_kmh":
                    speed_kmh,

                "geometry":
                    segment_geometry,

                "coordinate_order":
                    "lon_lat",

                "source":
                    "tmap_current",

            })


            sequence += 1


    return traffic_segments
'''


# ============================================================
# 5. Traffic 함수 삽입
#
# extract_route_geometry 다음,
# extract_route_summary 전에 삽입
# ============================================================

ANCHOR_1 = """# ============================================================
# 7. TMAP Summary 추출
# ============================================================
"""


if ANCHOR_1 not in text:

    raise RuntimeError(
        "Traffic 함수 삽입 위치를 찾지 못했습니다.\n"
        "route_engine_phase2_current.py가 예상 버전과 다릅니다."
    )


text = text.replace(

    ANCHOR_1,

    TRAFFIC_FUNCTION
    + "\n\n"
    + ANCHOR_1,

    1,

)


# ============================================================
# 6. Navigation Guidance 생성 직후
#    Traffic Segments 생성
# ============================================================

ANCHOR_2 = """    navigation_guidance = (
        extract_navigation_guidance(
            features,
            geometry,
        )
    )


"""


TRAFFIC_BUILD = """    # ========================================================
    # TMAP Current Traffic
    #
    # 현재 경로 응답에 포함된 교통상태를
    # Geometry 구간별로 추출한다.
    #
    # AI 미래예측값이 아니다.
    # ========================================================

    traffic_segments = (
        extract_tmap_traffic_segments(
            features
        )
    )


"""


if ANCHOR_2 not in text:

    raise RuntimeError(
        "Navigation Guidance 위치를 찾지 못했습니다."
    )


text = text.replace(

    ANCHOR_2,

    ANCHOR_2
    + TRAFFIC_BUILD,

    1,

)


# ============================================================
# 7. Route 반환 JSON에 Traffic 추가
# ============================================================

ANCHOR_3 = """        "navigation_schema_version":
            "navigation_guidance_v1",

        "source":
            "tmap",
"""


TRAFFIC_RETURN = """        "navigation_schema_version":
            "navigation_guidance_v1",

        # ====================================================
        # TMAP Current Traffic
        # ====================================================

        "traffic_segments":
            traffic_segments,

        "traffic_segment_count":
            len(
                traffic_segments
            ),

        "traffic_schema_version":
            "tmap_current_traffic_v1",

        "traffic_source":
            "tmap_current",

        "source":
            "tmap",
"""


if ANCHOR_3 not in text:

    raise RuntimeError(
        "Route 반환 JSON 위치를 찾지 못했습니다."
    )


text = text.replace(

    ANCHOR_3,

    TRAFFIC_RETURN,

    1,

)


# ============================================================
# 8. 콘솔 출력에 Traffic Segment 개수 추가
# ============================================================

ANCHOR_4 = """            f"{route['geometry_point_count']} points | "
            f"{route['navigation_guidance_count']} guidance"
"""


TRAFFIC_PRINT = """            f"{route['geometry_point_count']} points | "
            f"{route['navigation_guidance_count']} guidance | "
            f"{route['traffic_segment_count']} traffic segments"
"""


if ANCHOR_4 in text:

    text = text.replace(

        ANCHOR_4,

        TRAFFIC_PRINT,

        1,

    )


# ============================================================
# 9. Phase 2 최종 route_engine.py 저장
# ============================================================

TARGET.write_text(

    text,

    encoding="utf-8",

)


print(
    "Phase 2 route_engine.py 생성 완료."
)

print()
print(TARGET)
print()


# ============================================================
# 10. Python 문법 검사
# ============================================================

py_compile.compile(

    str(
        TARGET
    ),

    doraise=True,

)


print(
    "Python 문법 검사: PASS"
)


# ============================================================
# 11. 최종 확인
# ============================================================

final_text = TARGET.read_text(
    encoding="utf-8",
)


required_tokens = [

    "def extract_tmap_traffic_segments",

    '"traffic_segments"',

    '"traffic_segment_count"',

    '"traffic_schema_version"',

    '"traffic_source"',

    '"navigation_guidance"',

    '"navigation_schema_version"',

]


missing = [

    token

    for token
    in required_tokens

    if token
    not in final_text

]


if missing:

    raise RuntimeError(
        "최종 파일 검증 실패: "
        + ", ".join(
            missing
        )
    )


print(
    "Traffic + Navigation 보존 검사: PASS"
)

print()
print(
    "========================================"
)

print(
    "PHASE 2 route_engine 준비 완료"
)

print(
    "========================================"
)