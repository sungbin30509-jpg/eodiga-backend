from pathlib import Path
import shutil


# ============================================================
# PHASE 2 Flutter
# 실제 TMAP 현재 교통상태 구간별 색상 표시
#
# Phase 1은 절대 수정하지 않는다.
# ============================================================


TARGET = Path(
    r"C:\flow\eonjaega_merged_phase2"
    r"\lib\widgets\real_route_navigation_panel.dart"
)

BACKUP = Path(
    r"C:\flow\eonjaega_merged_phase2"
    r"\lib\widgets"
    r"\real_route_navigation_panel.before_traffic.dart.bak"
)


# ============================================================
# 1. 대상 확인
# ============================================================

if not TARGET.exists():
    raise FileNotFoundError(
        f"Phase 2 Flutter 파일을 찾을 수 없습니다:\n{TARGET}"
    )


print()
print("========================================")
print("PHASE 2 Flutter Traffic Patch")
print("========================================")
print()

print("TARGET:")
print(TARGET)
print()


# ============================================================
# 2. 백업
# ============================================================

shutil.copy2(
    TARGET,
    BACKUP,
)

print("백업 완료:")
print(BACKUP)
print()


# ============================================================
# 3. 현재 파일 읽기
# ============================================================

text = TARGET.read_text(
    encoding="utf-8",
)


# 이미 적용된 경우 중단
if "class _TrafficLegend extends StatelessWidget" in text:
    raise RuntimeError(
        "이미 TMAP Traffic 지도 코드가 적용되어 있습니다."
    )


# ============================================================
# 4. 기존 SelectedRouteMap 블록 찾기
# ============================================================

START_TOKEN = (
    "class _SelectedRouteMap extends StatelessWidget {"
)

END_TOKEN = (
    "class _RouteMetrics extends StatelessWidget {"
)


start = text.find(
    START_TOKEN
)

end = text.find(
    END_TOKEN
)


if start < 0:
    raise RuntimeError(
        "_SelectedRouteMap 시작 위치를 찾지 못했습니다."
    )


if end < 0:
    raise RuntimeError(
        "_RouteMetrics 시작 위치를 찾지 못했습니다."
    )


if end <= start:
    raise RuntimeError(
        "Flutter 클래스 위치가 올바르지 않습니다."
    )


# ============================================================
# 5. 새로운 교통상태 지도
# ============================================================

NEW_MAP_BLOCK = r'''
class _SelectedRouteMap extends StatelessWidget {
  const _SelectedRouteMap({
    required this.route,
    required this.plan,
  });

  final Map<String, dynamic> route;
  final CommutePlan plan;

  // ----------------------------------------------------------
  // TMAP 현재 교통상태 색상
  //
  // 0 = 정보없음
  // 1 = 원활
  // 2 = 서행
  // 3 = 지체
  // 4 = 정체
  // ----------------------------------------------------------

  static const Color _trafficUnknown =
      Color(0xFF9CA3AF);

  static const Color _trafficSmooth =
      Color(0xFF16A34A);

  static const Color _trafficSlow =
      Color(0xFFF59E0B);

  static const Color _trafficDelay =
      Color(0xFFEA580C);

  static const Color _trafficCongested =
      Color(0xFFDC2626);


  // ----------------------------------------------------------
  // [lon, lat]
  // →
  // LatLng(lat, lon)
  // ----------------------------------------------------------

  List<LatLng> _parseGeometry(
    dynamic raw,
  ) {
    final points = <LatLng>[];

    if (raw is! List) {
      return points;
    }

    for (final item in raw) {
      if (
          item is List &&
          item.length >= 2 &&
          item[0] is num &&
          item[1] is num
      ) {
        points.add(
          LatLng(
            (item[1] as num).toDouble(),
            (item[0] as num).toDouble(),
          ),
        );
      }
    }

    return points;
  }


  // ----------------------------------------------------------
  // congestion_level
  // →
  // 지도 색상
  // ----------------------------------------------------------

  Color _trafficColor(
    dynamic value,
  ) {
    final level = value is num
        ? value.toInt()
        : int.tryParse(
            value?.toString() ?? '',
          );

    return switch (level) {
      1 => _trafficSmooth,
      2 => _trafficSlow,
      3 => _trafficDelay,
      4 => _trafficCongested,
      _ => _trafficUnknown,
    };
  }


  // ----------------------------------------------------------
  // traffic_segments
  // →
  // 여러 개의 Polyline
  // ----------------------------------------------------------

  List<Polyline> _buildTrafficPolylines() {
    final rawSegments =
        route['traffic_segments'];

    if (
        rawSegments is! List ||
        rawSegments.isEmpty
    ) {
      return const [];
    }

    final polylines = <Polyline>[];


    for (final rawSegment in rawSegments) {
      if (rawSegment is! Map) {
        continue;
      }

      final segment =
          Map<String, dynamic>.from(
        rawSegment,
      );

      final segmentPoints =
          _parseGeometry(
        segment['geometry'],
      );


      if (segmentPoints.length < 2) {
        continue;
      }


      polylines.add(
        Polyline(
          points: segmentPoints,
          strokeWidth: 7,
          color: _trafficColor(
            segment['congestion_level'],
          ),
        ),
      );
    }


    return polylines;
  }


  @override
  Widget build(
    BuildContext context,
  ) {
    // 전체 Route geometry
    final points =
        _parseGeometry(
      route['geometry'],
    );


    if (points.isEmpty) {
      return const Center(
        child: Text(
          'Geometry가 없습니다.',
        ),
      );
    }


    // TMAP 현재 교통정보 Polyline
    final trafficPolylines =
        _buildTrafficPolylines();


    final hasTrafficSegments =
        trafficPolylines.isNotEmpty;


    // --------------------------------------------------------
    // 출발 / 도착 Marker
    // --------------------------------------------------------

    final markers = <Marker>[];

    final origin =
        plan.originPlace;

    final destination =
        plan.destinationPlace;


    if (
        origin?.latitude != null &&
        origin?.longitude != null
    ) {
      markers.add(
        Marker(
          point: LatLng(
            origin!.latitude!,
            origin.longitude!,
          ),
          width: 44,
          height: 44,
          child: const Icon(
            Icons.trip_origin,
            size: 30,
            color: Color(
              0xFF2563EB,
            ),
          ),
        ),
      );
    }


    if (
        destination?.latitude != null &&
        destination?.longitude != null
    ) {
      markers.add(
        Marker(
          point: LatLng(
            destination!.latitude!,
            destination.longitude!,
          ),
          width: 44,
          height: 44,
          child: const Icon(
            Icons.location_on,
            size: 36,
            color: Color(
              0xFFDC2626,
            ),
          ),
        ),
      );
    }


    final routeId =
        route['route_id']
            ?.toString() ??
        '-';


    final trafficCount =
        route['traffic_segment_count']
            ?.toString() ??
        '0';


    return ClipRRect(
      borderRadius:
          BorderRadius.circular(
        16,
      ),
      child: Stack(
        children: [

          // ==================================================
          // 지도
          // ==================================================

          Positioned.fill(
            child: FlutterMap(
              key: ValueKey(
                '$routeId-'
                '${points.length}-'
                '$trafficCount-'
                '$hasTrafficSegments',
              ),

              options: MapOptions(
                initialCameraFit:
                    CameraFit.bounds(
                  bounds:
                      LatLngBounds.fromPoints(
                    points,
                  ),
                  padding:
                      const EdgeInsets.all(
                    44,
                  ),
                ),
              ),

              children: [

                // -------------------------------------------
                // OSM 배경지도
                // -------------------------------------------

                TileLayer(
                  urlTemplate:
                      'https://tile.openstreetmap.org/{z}/{x}/{y}.png',
                  userAgentPackageName:
                      'flow_app',
                ),


                // -------------------------------------------
                // 전체 Route 기본선
                //
                // Traffic이 있더라도 아주 얇은 기본선을
                // 아래에 깔아 Route 단절을 방지.
                // -------------------------------------------

                PolylineLayer(
                  polylines: [
                    Polyline(
                      points: points,
                      strokeWidth: 5,
                      color:
                          hasTrafficSegments
                              ? const Color(
                                  0xFFD1D5DB,
                                )
                              : FlowColors.primary,
                    ),
                  ],
                ),


                // -------------------------------------------
                // TMAP 현재 Traffic
                // -------------------------------------------

                if (hasTrafficSegments)
                  PolylineLayer(
                    polylines:
                        trafficPolylines,
                  ),


                // -------------------------------------------
                // 출발 / 도착
                // -------------------------------------------

                if (markers.isNotEmpty)
                  MarkerLayer(
                    markers: markers,
                  ),


                RichAttributionWidget(
                  attributions: [
                    TextSourceAttribution(
                      'OpenStreetMap contributors',
                    ),
                  ],
                ),
              ],
            ),
          ),


          // ==================================================
          // Traffic Legend
          // ==================================================

          Positioned(
            left: 12,
            bottom: 12,
            child: _TrafficLegend(
              hasTrafficSegments:
                  hasTrafficSegments,
            ),
          ),
        ],
      ),
    );
  }
}


// ============================================================
// 현재 교통상태 범례
// ============================================================

class _TrafficLegend
    extends StatelessWidget {
  const _TrafficLegend({
    required this.hasTrafficSegments,
  });

  final bool hasTrafficSegments;


  @override
  Widget build(
    BuildContext context,
  ) {
    return IgnorePointer(
      child: Container(
        constraints:
            const BoxConstraints(
          maxWidth: 330,
        ),

        padding:
            const EdgeInsets.symmetric(
          horizontal: 12,
          vertical: 10,
        ),

        decoration: BoxDecoration(
          color:
              Colors.white.withOpacity(
            0.94,
          ),

          borderRadius:
              BorderRadius.circular(
            12,
          ),

          border: Border.all(
            color:
                FlowColors.border,
          ),

          boxShadow: const [
            BoxShadow(
              blurRadius: 10,
              offset:
                  Offset(
                0,
                3,
              ),
              color:
                  Color(
                0x1A000000,
              ),
            ),
          ],
        ),

        child: Column(
          crossAxisAlignment:
              CrossAxisAlignment.start,

          mainAxisSize:
              MainAxisSize.min,

          children: [

            const Text(
              '현재 교통상태 · TMAP',
              style: TextStyle(
                fontSize: 12,
                fontWeight:
                    FontWeight.w800,
              ),
            ),

            const SizedBox(
              height: 7,
            ),


            if (hasTrafficSegments)

              const Wrap(
                spacing: 10,
                runSpacing: 6,
                children: [

                  _TrafficLegendItem(
                    color:
                        Color(
                      0xFF16A34A,
                    ),
                    label:
                        '원활',
                  ),

                  _TrafficLegendItem(
                    color:
                        Color(
                      0xFFF59E0B,
                    ),
                    label:
                        '서행',
                  ),

                  _TrafficLegendItem(
                    color:
                        Color(
                      0xFFEA580C,
                    ),
                    label:
                        '지체',
                  ),

                  _TrafficLegendItem(
                    color:
                        Color(
                      0xFFDC2626,
                    ),
                    label:
                        '정체',
                  ),

                  _TrafficLegendItem(
                    color:
                        Color(
                      0xFF9CA3AF,
                    ),
                    label:
                        '정보없음',
                  ),
                ],
              )

            else

              const Text(
                '현재 TMAP 구간 교통정보 없음 · 기본 경로 표시',
                style: TextStyle(
                  fontSize: 11,
                  color:
                      FlowColors
                          .textSecondary,
                ),
              ),
          ],
        ),
      ),
    );
  }
}


// ============================================================
// 범례 Item
// ============================================================

class _TrafficLegendItem
    extends StatelessWidget {
  const _TrafficLegendItem({
    required this.color,
    required this.label,
  });

  final Color color;
  final String label;


  @override
  Widget build(
    BuildContext context,
  ) {
    return Row(
      mainAxisSize:
          MainAxisSize.min,

      children: [

        Container(
          width: 16,
          height: 5,

          decoration:
              BoxDecoration(
            color: color,

            borderRadius:
                BorderRadius.circular(
              99,
            ),
          ),
        ),

        const SizedBox(
          width: 4,
        ),

        Text(
          label,
          style:
              const TextStyle(
            fontSize: 10,
            fontWeight:
                FontWeight.w600,
          ),
        ),
      ],
    );
  }
}


'''


# ============================================================
# 6. 교체
# ============================================================

final_text = (
    text[:start]
    + NEW_MAP_BLOCK
    + text[end:]
)


# ============================================================
# 7. 저장
# ============================================================

TARGET.write_text(
    final_text,
    encoding="utf-8",
)


print(
    "Phase 2 Flutter Traffic 지도 코드 적용 완료."
)

print()
print(TARGET)
print()


# ============================================================
# 8. 간단 검증
# ============================================================

required_tokens = [
    "traffic_segments",
    "congestion_level",
    "_TrafficLegend",
    "현재 교통상태 · TMAP",
    "_NavigationBanner",
    "startNavigation",
]


missing = [
    token
    for token in required_tokens
    if token not in final_text
]


if missing:
    raise RuntimeError(
        "Flutter 최종 검사 실패: "
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
    "PHASE 2 Flutter 지도 수정 완료"
)

print(
    "========================================"
)