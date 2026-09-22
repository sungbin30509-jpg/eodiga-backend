import os
import pandas as pd


# ============================================================
# 파일 경로
# ============================================================

CSV_FILE = os.path.join(
    "data",
    "routes",
    "route_test_001_repaired_links.csv"
)


# ============================================================
# 파일 확인
# ============================================================

print()
print("======================================")
print("자동 삽입 LINK 검증")
print("======================================")


if not os.path.exists(CSV_FILE):

    print("파일을 찾을 수 없습니다.")
    print("경로:", CSV_FILE)

    raise SystemExit


# ============================================================
# CSV 읽기
# ============================================================

df = pd.read_csv(
    CSV_FILE
)


# ============================================================
# repair_inserted 값 정리
#
# CSV에서는 True가 문자열로 들어갈 수도 있어서
# 둘 다 처리
# ============================================================

inserted = df[
    df["repair_inserted"]
    .astype(str)
    .str.lower()
    .eq("true")
].copy()


# ============================================================
# 결과 출력
# ============================================================

print()
print(
    "자동 삽입 LINK 개수:",
    len(inserted),
    "개"
)


print()
print("======================================")
print("자동 삽입 LINK 목록")
print("======================================")


for _, row in inserted.iterrows():

    distance = row[
        "distance_to_tmap_m"
    ]

    # --------------------------------------------------------
    # 거리 기준 간단 판정
    # --------------------------------------------------------

    if pd.isna(distance):

        status = "⚠️ 거리정보 없음"

    elif distance <= 30:

        status = "✅ 매우 양호"

    elif distance <= 60:

        status = "✅ 양호"

    elif distance <= 100:

        status = "⚠️ 확인 필요"

    else:

        status = "❌ 의심"


    print()

    print(
        "sequence:",
        row["sequence"]
    )

    print(
        "LINK_ID:",
        row["LINK_ID"]
    )

    print(
        "도로명:",
        row["ROAD_NAME"]
    )

    print(
        "F_NODE:",
        row["F_NODE"]
    )

    print(
        "T_NODE:",
        row["T_NODE"]
    )

    print(
        "TMAP 경로와 거리:",
        distance,
        "m"
    )

    print(
        "판정:",
        status
    )


# ============================================================
# 통계
# ============================================================

valid_distance = (
    inserted[
        "distance_to_tmap_m"
    ]
    .dropna()
)


print()
print("======================================")
print("자동 삽입 LINK 거리 통계")
print("======================================")


if len(valid_distance) > 0:

    print(
        "평균 거리:",
        round(
            valid_distance.mean(),
            2
        ),
        "m"
    )

    print(
        "최대 거리:",
        round(
            valid_distance.max(),
            2
        ),
        "m"
    )

    print(
        "최소 거리:",
        round(
            valid_distance.min(),
            2
        ),
        "m"
    )


    suspicious = (
        valid_distance > 100
    ).sum()


    print(
        "100m 초과 LINK:",
        suspicious,
        "개"
    )


else:

    print(
        "거리 정보를 확인할 수 없습니다."
    )


print()
print("======================================")
print("검증 완료")
print("======================================")