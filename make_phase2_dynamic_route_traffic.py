from pathlib import Path
import shutil
import py_compile


# ============================================================
# PHASE 2
# Dynamic Route Service
# TMAP Current Traffic 전달 패치
#
# Phase 1은 절대 수정하지 않는다.
# ============================================================


ROOT = Path(__file__).resolve().parent


SOURCE = (
    ROOT
    / "dynamic_route_service_phase2_current.py"
)


TARGET = (
    ROOT
    / "backend"
    / "services"
    / "dynamic_route_service.py"
)


BACKUP = (
    ROOT
    / "backend"
    / "services"
    / "dynamic_route_service.before_phase2_traffic.py.bak"
)


# ============================================================
# 1. 파일 확인
# ============================================================

if not SOURCE.exists():

    raise FileNotFoundError(
        f"원본 파일이 없습니다:\n{SOURCE}"
    )


if not TARGET.exists():

    raise FileNotFoundError(
        f"Phase 2 dynamic_route_service.py가 없습니다:\n{TARGET}"
    )


print()

print(
    "========================================"
)

print(
    "PHASE 2 Dynamic Route Traffic Patch"
)

print(
    "========================================"
)

print()

print(
    "SOURCE:"
)

print(
    SOURCE
)

print()

print(
    "TARGET:"
)

print(
    TARGET
)

print()


# ============================================================
# 2. 기존 Phase 2 파일 백업
# ============================================================

shutil.copy2(
    TARGET,
    BACKUP,
)


print(
    "기존 Phase 2 dynamic_route_service.py 백업 완료:"
)

print(
    BACKUP
)

print()


# ============================================================
# 3. 검증본 읽기
# ============================================================

text = SOURCE.read_text(
    encoding="utf-8"
)


# ============================================================
# 이미 적용됐는지 확인
# ============================================================

if (
    '"traffic_segments"'
    in text
):

    raise RuntimeError(
        "dynamic_route_service_phase2_current.py에 "
        "이미 traffic_segments 코드가 있습니다."
    )


# ============================================================
# 4. route에서 traffic_segments 읽기
#
# 기존:
#
# geometry
# navigation_guidance
# frontend_routes.append
#
# 사이에 traffic_segments 추가
# ============================================================

ANCHOR_1 = """        navigation_guidance = (
            route.get(
                "navigation_guidance",
                [],
            )
        )


        frontend_routes.append({
"""


REPLACEMENT_1 = """        navigation_guidance = (
            route.get(
                "navigation_guidance",
                [],
            )
        )


        # --------------------------------------------------------
        # TMAP Current Traffic
        #
        # route_engine.py에서 추출한 현재 교통구간.
        #
        # AI 미래예측값이 아니라
        # TMAP 현재 교통정보이다.
        # --------------------------------------------------------

        traffic_segments = (
            route.get(
                "traffic_segments",
                [],
            )
        )


        if not isinstance(
            traffic_segments,
            list,
        ):

            traffic_segments = []


        frontend_routes.append({
"""


if ANCHOR_1 not in text:

    raise RuntimeError(
        "traffic_segments 로드 위치를 찾지 못했습니다."
    )


text = text.replace(
    ANCHOR_1,
    REPLACEMENT_1,
    1,
)


# ============================================================
# 5. Flutter Route JSON에 Traffic 추가
#
# Navigation 다음
# Mapping 전에 삽입
# ============================================================

ANCHOR_2 = """            "navigation_schema_version":
                route.get(
                    "navigation_schema_version",
                    "navigation_guidance_v1",
                ),

            # -----------------------------------------------
            # Mapping
"""


REPLACEMENT_2 = """            "navigation_schema_version":
                route.get(
                    "navigation_schema_version",
                    "navigation_guidance_v1",
                ),

            # -----------------------------------------------
            # TMAP Current Traffic
            #
            # 현재 교통상태이다.
            # AI 미래 혼잡예측과 구분한다.
            # -----------------------------------------------

            "traffic_segment_count":
                len(
                    traffic_segments
                ),

            "traffic_segments":
                traffic_segments,

            "traffic_schema_version":
                route.get(
                    "traffic_schema_version",
                    "tmap_current_traffic_v1",
                ),

            "traffic_source":
                route.get(
                    "traffic_source",
                    "tmap_current",
                ),

            "has_current_traffic":
                bool(
                    traffic_segments
                ),

            # -----------------------------------------------
            # Mapping
"""


if ANCHOR_2 not in text:

    raise RuntimeError(
        "Flutter Traffic 응답 삽입 위치를 찾지 못했습니다."
    )


text = text.replace(
    ANCHOR_2,
    REPLACEMENT_2,
    1,
)


# ============================================================
# 6. 최종 Phase 2 파일 저장
# ============================================================

TARGET.write_text(
    text,
    encoding="utf-8",
)


print(
    "Phase 2 dynamic_route_service.py 생성 완료."
)

print()

print(
    TARGET
)

print()


# ============================================================
# 7. Python 문법 검사
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
# 8. 최종 필드 검사
# ============================================================

final_text = TARGET.read_text(
    encoding="utf-8"
)


required_tokens = [

    '"geometry"',

    '"navigation_guidance"',

    '"traffic_segments"',

    '"traffic_segment_count"',

    '"traffic_schema_version"',

    '"traffic_source"',

    '"has_current_traffic"',

    '"mapping_status"',

    '"ai_link_coverage_percent"',

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
    "Geometry + Navigation + Traffic + Mapping 보존 검사: PASS"
)

print()

print(
    "========================================"
)

print(
    "PHASE 2 dynamic_route_service 준비 완료"
)

print(
    "========================================"
)