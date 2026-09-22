from typing import Any
from uuid import uuid4

from fastapi import (
    APIRouter,
    HTTPException,
)

from pydantic import (
    BaseModel,
)

from backend.services.navigation_service import (
    get_navigation_state,
)


# ============================================================
# FLOW:MATE Navigation API
#
# 선택된 Route
# →
# Navigation Session 생성
# →
# GPS Update
# →
# Turn-by-Turn 안내 반환
#
# 주의:
# /start 이후 /update에서는 TMAP API를 다시 호출하지 않는다.
# ============================================================


router = APIRouter(
    prefix="/api/navigation",
    tags=["navigation"],
)


# ============================================================
# MVP Navigation Session
#
# 서버 메모리에만 저장.
# FastAPI 재시작 시 세션은 초기화됨.
# ============================================================

NAVIGATION_SESSIONS: dict[str, dict[str, Any]] = {}


# ============================================================
# Request Models
# ============================================================

class NavigationStartRequest(BaseModel):

    route: dict[str, Any]


class NavigationUpdateRequest(BaseModel):

    session_id: str

    current_lat: float

    current_lon: float


# ============================================================
# POST /api/navigation/start
#
# Flutter에서 사용자가 선택한 Route를 전달한다.
#
# route 안에는 최소:
#
# geometry
# navigation_guidance
#
# 가 있어야 한다.
# ============================================================

@router.post(
    "/start"
)
def navigation_start(
    request: NavigationStartRequest,
):

    route = request.route


    geometry = route.get(
        "geometry"
    )

    navigation_guidance = route.get(
        "navigation_guidance"
    )


    if not geometry:

        raise HTTPException(
            status_code=400,
            detail=(
                "Route에 geometry가 없습니다."
            ),
        )


    if not navigation_guidance:

        raise HTTPException(
            status_code=400,
            detail=(
                "Route에 navigation_guidance가 없습니다."
            ),
        )


    session_id = (
        uuid4().hex
    )


    NAVIGATION_SESSIONS[
        session_id
    ] = {

        "route":
            route,

    }


    return {

        "status":
            "started",

        "session_id":
            session_id,

        "candidate_id":
            route.get(
                "candidate_id"
            ),

        "route_label":
            route.get(
                "route_label"
            ),

        "total_distance_m":
            route.get(
                "total_distance_m"
            ),

        "tmap_eta_min":
            route.get(
                "tmap_eta_min"
            ),

        "geometry_point_count":
            len(
                geometry
            ),

        "navigation_guidance_count":
            len(
                navigation_guidance
            ),

    }


# ============================================================
# POST /api/navigation/update
#
# GPS가 갱신될 때마다 호출.
#
# TMAP 신규 호출 없음.
#
# 현재 GPS
# →
# Route에 Snap
# →
# 다음 Guidance 탐색
# →
# 남은 거리
# →
# 안내문 반환
# ============================================================

@router.post(
    "/update"
)
def navigation_update(
    request: NavigationUpdateRequest,
):

    session = (
        NAVIGATION_SESSIONS.get(
            request.session_id
        )
    )


    if session is None:

        raise HTTPException(
            status_code=404,
            detail=(
                "Navigation session을 찾을 수 없습니다. "
                "서버가 재시작되었다면 navigation/start를 "
                "다시 호출해야 합니다."
            ),
        )


    route = session[
        "route"
    ]


    try:

        navigation_state = (
            get_navigation_state(

                route=route,

                current_lat=(
                    request.current_lat
                ),

                current_lon=(
                    request.current_lon
                ),

            )
        )


    except Exception as error:

        raise HTTPException(
            status_code=500,
            detail=(
                "Navigation 상태 계산 실패: "
                f"{error}"
            ),
        ) from error


    return {

        "session_id":
            request.session_id,

        "candidate_id":
            route.get(
                "candidate_id"
            ),

        **navigation_state,

    }


# ============================================================
# GET /api/navigation/sessions/{session_id}
#
# 디버깅용
# ============================================================

@router.get(
    "/sessions/{session_id}"
)
def navigation_session_detail(
    session_id: str,
):

    session = (
        NAVIGATION_SESSIONS.get(
            session_id
        )
    )


    if session is None:

        raise HTTPException(
            status_code=404,
            detail=(
                "Navigation session을 찾을 수 없습니다."
            ),
        )


    route = session[
        "route"
    ]


    geometry = (
        route.get(
            "geometry",
            []
        )
    )

    navigation_guidance = (
        route.get(
            "navigation_guidance",
            []
        )
    )


    return {

        "status":
            "active",

        "session_id":
            session_id,

        "candidate_id":
            route.get(
                "candidate_id"
            ),

        "route_label":
            route.get(
                "route_label"
            ),

        "total_distance_m":
            route.get(
                "total_distance_m"
            ),

        "tmap_eta_min":
            route.get(
                "tmap_eta_min"
            ),

        "geometry_point_count":
            len(
                geometry
            ),

        "navigation_guidance_count":
            len(
                navigation_guidance
            ),

        # ----------------------------------------------------
        # 디버깅용 원본 Navigation 데이터
        # ----------------------------------------------------

        "geometry":
            geometry,

        "navigation_guidance":
            navigation_guidance,

    }
