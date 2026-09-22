from flask import Flask
from flask import render_template
from flask import request

from tmap_service import search_place
from tmap_service import get_route
from tmap_service import APP_KEY


# ============================================================
# Flask 앱 생성
# ============================================================

app = Flask(__name__)


# ============================================================
# 메인 페이지
# ============================================================

@app.route("/", methods=["GET", "POST"])
def home():

    destination = None
    route = None
    error = None

    start_latitude = None
    start_longitude = None


    # ========================================================
    # 사용자가 경로 검색 버튼을 눌렀을 때
    # ========================================================

    if request.method == "POST":

        # ----------------------------------------------------
        # 목적지
        # ----------------------------------------------------

        keyword = request.form.get(
            "destination",
            ""
        ).strip()


        # ----------------------------------------------------
        # 브라우저 GPS에서 받은 현재 위치
        # ----------------------------------------------------

        start_latitude_text = request.form.get(
            "start_latitude",
            ""
        ).strip()

        start_longitude_text = request.form.get(
            "start_longitude",
            ""
        ).strip()


        print()
        print("======================================")
        print("FLOWMATE 웹 경로 검색")
        print("======================================")

        print("입력 목적지:", keyword)
        print("현재 위도:", start_latitude_text)
        print("현재 경도:", start_longitude_text)


        # ----------------------------------------------------
        # 목적지 확인
        # ----------------------------------------------------

        if not keyword:

            error = "목적지를 입력해주세요."


        # ----------------------------------------------------
        # GPS 확인
        # ----------------------------------------------------

        elif not start_latitude_text or not start_longitude_text:

            error = "현재 위치를 가져오지 못했습니다."


        else:

            try:

                start_latitude = float(
                    start_latitude_text
                )

                start_longitude = float(
                    start_longitude_text
                )


            except ValueError:

                error = "현재 위치 좌표가 올바르지 않습니다."


        # ----------------------------------------------------
        # 정상적으로 입력된 경우
        # ----------------------------------------------------

        if error is None:

            # =================================================
            # 1. 목적지 검색
            # =================================================

            destination = search_place(
                keyword
            )


            if destination is None:

                error = "목적지를 찾을 수 없습니다."


            else:

                print(
                    "검색된 목적지:",
                    destination["name"]
                )


                # =============================================
                # 2. 현재 위치 → 목적지 경로 탐색
                # =============================================

                route = get_route(

                    start_longitude,
                    start_latitude,

                    destination["longitude"],
                    destination["latitude"],

                    destination["name"]
                )


                if route is None:

                    error = "경로 탐색에 실패했습니다."


    # ========================================================
    # 웹페이지 출력
    # ========================================================

    return render_template(

        "index.html",

        destination=destination,

        route=route,

        error=error,

        start_latitude=start_latitude,

        start_longitude=start_longitude,
        tmap_app_key=APP_KEY
    )


# ============================================================
# Flask 서버 실행
# ============================================================

if __name__ == "__main__":

    app.run(
        debug=True
    )