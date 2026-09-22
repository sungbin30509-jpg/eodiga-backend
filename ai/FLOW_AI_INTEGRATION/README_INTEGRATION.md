# FLOW AI Integration Package — TMAP route → 표준 LINK_ID → 미래 속도 예측

대상: TMAP 경로 생성 및 TMAP ↔ 국가표준노드링크 LINK_ID 매핑을 담당하는 팀원.
이 폴더만 있으면 팀원 PC에서 `LINK_ID 목록 + request_time + target_time 목록 → 링크별 예측 속도`가 바로 동작합니다.

> **이 모델은 provisional INTEGRATION DEMO MODEL입니다.** FINAL 모델이 아니고 성능 평가를 거치지 않았습니다(11장).
> **Traffic Response(잠재수요 → before/after speed)는 이번 데모에 포함되지 않습니다**(12장).

## 0. 폴더 구성

| 경로 | 내용 |
|---|---|
| `artifact/` | 학습된 LightGBM(`model/global.txt`) + 히스토리 프로파일 + 캘린더 + `bundle.json`(sha256, 지원 링크, feature 목록, 설정). 수정 금지(digest 검증됨) |
| `flow_traffic/` | 추론 코드. `TrafficPredictor` (`flow_traffic/inference.py`) 및 feature 생성기 |
| `flow_context.py` | 최근 교통관측(ITS/GITS)·날씨·캘린더를 `set_context()` 형식으로 바꾸는 어댑터 |
| `src/` | GITS 실시간 API 클라이언트(원 저장소 코드 그대로). `--context gits-live`에서만 사용 |
| `context/` | 실제 관측 샘플: ITS 2026-08-28~31(355링크), GITS 스냅샷 2026-09-10 20:4x, ASOS 날씨 8/25~9/1, 캘린더 |
| `supported_links.csv` | 현재 모델이 학습한 355개 LINK_ID + 도로명/노드명/좌표 |
| `integration_example.py` | 최소 실행 예제 (load → set_context → predict_traffic) |
| `requirements.txt`, `.env.example`, `MANIFEST.json` | 의존성, (선택) GITS 키 변수명, 파일 sha256 |

## 1. 설치

Python 3.11+ (검증: 3.14.7, Windows 11). 프로젝트 저장소 없이 이 폴더만으로 동작합니다.

```bash
cd FLOW_AI_INTEGRATION
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
.venv\Scripts\python.exe integration_example.py
```

마지막 명령의 마지막 줄이 `20/25 predictions via model; OK`, exit code 0이면 정상입니다(5건은 의도적 미지원 링크 `9999999999` 폴백 시연).

## 2. Predictor 초기화

```python
import sys; sys.path.insert(0, "<FLOW_AI_INTEGRATION 경로>")
from flow_traffic.inference import TrafficPredictor
import flow_context as fc

pred = TrafficPredictor.load("<FLOW_AI_INTEGRATION>/artifact")   # bundle.json의 sha256으로 파일 검증
pred.meta["known_links"]      # 지원 355 LINK_ID (list[str])
pred.meta["run_id"]           # "integration_demo_01" (model_version)
```

프로세스당 한 번 load 하고 재사용하세요(로드 ~0.2초, 예측은 링크×target 수십 건에 수십 ms).

## 3. 현재 교통 context 공급 (가장 중요)

모델 경로(`output_method=model`)가 되려면 **request_time 기준 60분 이내**의 해당 링크 속도 관측이 `set_context()`로 들어와 있어야 합니다. 없으면 히스토리 프로파일 폴백(`fallback_baseline`)입니다. 가짜 관측을 만들어 넣지 마세요.

```python
history = ...            # DataFrame: timestamp(KST naive, 5분 슬롯), link_id(str 10자리), speed(km/h)
weather = fc.empty_weather()   # 또는 fc.load_weather(parquet) — 없어도 됨(wx_missing=1)
calendar = fc.calendar_through(pred.calendar, "2026-12-31")   # 9/30 이후 날짜 요청 시 필요
pred.set_context(history, weather, calendar)
```

history를 만드는 3가지 방법(모두 실제 관측):

| 방법 | 코드 | 비고 |
|---|---|---|
| A. GITS 실시간 (권장, 라이브 데모) | `history = fc.fetch_gits_live()` | 경기도 GITS `getRoadLinkTrafficInfoList` 4개 route 호출. **본인 GITS_API_KEY 필요**(`.env`에 `GITS_API_KEY=` 작성, `.env.example` 참고). 355링크 중 339~343개 커버. 키 발급: openapigits.gg.go.kr |
| B. 저장된 GITS 스냅샷 파일 | `history = fc.load_gits_snapshot("context/gits_snapshot_2026-09-10_2042KST.parquet")` | `collect_gits_realtime.py` 파티션 parquet/csv도 동일 함수로 변환. GITS 타임스탬프(초 단위)는 5분 슬롯으로 내림 |
| C. ITS 5분 히스토리 | `history = fc.load_its_history("context/its_history_tail_2026-08-28_to_08-31.parquet")` | 오프라인 재현용. request_time은 관측 마지막 시각 + 5분 이후여야 함 |

여러 소스는 `fc.merge_history(a, b)`로 합칠 수 있습니다. 라이브 운영 시에는 5분마다 `fetch_gits_live()` → `set_context()`를 갱신하세요(직전 결과들을 merge하면 lag/rolling feature가 채워져 정보량이 늘어납니다).

주의: **request_time은 2026-09-01 00:00 KST 이후**여야 합니다(모델 학습 정보 cutoff 가드, 그 이전은 ValueError). 과거 날짜 리플레이는 이 artifact로는 불가합니다.

## 4. TMAP 표준 LINK_ID를 넣는 위치

`predict_traffic(request_time, target_times, link_ids)`의 세 번째 인자입니다.

- 형식: 국가표준노드링크 LINK_ID **10자리 문자열** (예: `"2050019200"`). 정수면 `str()`로 변환. 중복 불가.
- GITS `linkId` == ITS `LINKID` == 표준노드링크 `LINK_ID` (동일 ID 체계, 감사 확인).
- 지원 여부는 `link_id in pred.meta["known_links"]` 또는 `supported_links.csv`로 사전 필터하세요. 미지원 링크도 호출은 가능하지만 8장의 폴백이 됩니다.
- 경로 전체를 넣어도 되고(호출 1회에 링크 N × target M), 성남 내부 구간만 걸러 넣어도 됩니다.

## 5. target_time 생성

- 절대 시각, **5분 단위 슬롯**(초·마이크로초 0, 분 % 5 == 0), request_time 이상. 중복 불가.
- `lead_minutes = target_time − request_time`. 학습 범위 5~480분. 그 밖은 폴백.
- tz-aware(`+09:00`)와 naive 모두 허용; naive는 KST로 해석.

```python
import pandas as pd
r = pd.Timestamp.now(tz="Asia/Seoul").floor("5min")
targets = [r + pd.Timedelta(minutes=m) for m in (5, 15, 30, 60, 90, 120)]
# 출발시각 flex 시나리오: 후보 출발시각 + TMAP api_travel_min 으로 각 링크 통과 예정 시각을 만들어 target으로 사용
```

## 6. predict_traffic() 호출

```python
res = pred.predict_traffic(r, targets, ["2050019200", "2050028700", "2060104700"])
# 반환: list[dict], 길이 = len(link_ids) * len(targets), 순서 = link 우선 → target
```

`request_time`이 최신 관측보다 오래되면 안 되고(미래 관측 누수 방지: 관측시각+5분 ≤ request_time인 것만 사용), 컨텍스트에 request_time 이후 데이터가 있어도 자동으로 무시됩니다.

## 7. 반환값 (요소 1개)

```json
{
 "request_time": "2026-09-10T20:50:00+09:00", "target_time": "2026-09-10T21:50:00+09:00", "lead_minutes": 60.0,
 "link_id": "2050019200", "predicted_speed_kmh": 83.8, "congestion_level": "free",
 "congestion_policy": "analytical_thresholds_not_official", "output_method": "model",
 "model_version": "integration_demo_01",
 "information_available_at": {"traffic_observation_time": "…", "traffic_available_at": "…", "weather_mode": "request_observed",
                              "weather_as_of": null, "historical_profile_version": "…", "profile_available_at": "…"},
 "lead_within_support": false, "within_provisional_training_range": true,
 "support_status": "unvalidated_provisional", "data_badge": "real"
}
```

- `output_method`: `model`(LightGBM) / `fallback_baseline`(히스토리 프로파일 median) / `live_observed`(lead 0이고 최신 관측 있을 때 관측값 그대로).
- `congestion_level`: 15/25/40 km/h 임계 → jam/slow/moderate/free (분석용 임계, 공식 기준 아님).
- `support_status`는 이 모델에서 항상 `unvalidated_provisional`, `lead_within_support`는 항상 false입니다(검증된 지원 범위를 선언하지 않음). 서비스 판단은 `within_provisional_training_range`와 `output_method`를 쓰세요.
- FLOW API `traffic_forecast.v4`의 `links[].predictions[]` 항목과 1:1로 대응합니다.

## 8. 지원되지 않는 LINK 처리

- 355개 밖의 LINK_ID → 예외 없이 `output_method=fallback_baseline`, `predicted_speed_kmh`는 전 링크 global median(43 km/h)이라 **의미 없는 값**입니다. UI에 쓰지 말고 `link not supported`로 처리하세요.
- 권장: 호출 전 `known = set(pred.meta["known_links"])`로 필터하고, 미지원 링크는 TMAP 자체 소요시간을 그대로 쓰는 등 별도 정책을 적용.
- 성남 내부 세그먼트 중 상당수가 아직 355개에 없습니다(coverage 감사 결과 약 40%). target universe v2로 재학습 예정.

## 9. fallback 처리

`fallback_baseline`이 나오는 이유는 네 가지뿐입니다(`integration_example.py`가 이유를 출력):

1. 미지원 링크(8장).
2. context에 그 링크의 request_time 이전 관측이 없음.
3. 최신 관측이 60분보다 오래됨(`obs_age_min > 60`).
4. lead가 5~480분 밖.

폴백 값은 요일유형×30분 슬롯 히스토리 median(3~8월)입니다. 값은 반환되지만 `output_method`를 반드시 확인해 UI에서 구분 표시하세요.

## 10. 현재 지원 355 link

`supported_links.csv` (link_id, route, corridor, 방향, 시작/끝 노드명, 길이, 좌표). 도로별: 밤고개로/대왕판교로/신수로 122, 분당수서로 112, 경부고속도로 63, 국도3호선 58. 370개 target 중 15개는 관측일 부족으로 제외되었습니다.

## 11. 이 모델의 성격 (provisional integration demo)

- 2026-03-02~08-31 평일 124일 ITS 5분 자료 전체로 1회 학습. train/validation/test 분리·지표 없음 → **정확도 보장 없음**.
- 355 링크는 잠정 universe. TMAP 실제 경로 coverage 확정 후 universe v2로 재학습하며, 그때 artifact를 교체하면 코드는 그대로입니다.
- 학습 정보 cutoff 2026-09-01 00:00 KST; 캘린더 확장(추석 등 9~12월 공휴일)은 `flow_context.HOLIDAYS_2026_Q4`에 있으며 검증 필요.
- 날씨 feature는 request 시점 ASOS 관측(수원 119/서울 108)입니다. 라이브에서 날씨를 안 넣으면 `wx_missing=1`로 동작합니다(학습 시엔 항상 있었으므로 약간의 분포 차이).

## 12. Traffic Response 미포함

이 패키지는 `LightGBM → baseline future traffic`까지입니다. 잠재 퇴근수요에 따른 before/after speed(Traffic Response)는 아직 calibration 전이며 포함되지 않았습니다. 반환된 `predicted_speed_kmh`를 수요 시나리오별로 가공하지 마세요.

## 문제 해결

| 증상 | 원인/조치 |
|---|---|
| `Artifact digest mismatch` | artifact 파일이 수정/손상됨. 원본을 다시 복사 |
| `Model trained after request cutoff` | request_time < 2026-09-01 00:00 KST |
| `Targets must be future/current 5-minute slots` | target이 5분 슬롯이 아니거나 request보다 과거 |
| `Calendar does not cover requested date` | `fc.calendar_through(pred.calendar, "<날짜>")`로 확장해 set_context에 전달 |
| `GITS_API_KEY is not set` | `.env`에 본인 키 작성(값은 절대 로그/커밋 금지) |
| 전부 fallback | context 관측이 없거나 60분 초과. `fc.latest_observation_age(history, r, links)`로 확인 |
