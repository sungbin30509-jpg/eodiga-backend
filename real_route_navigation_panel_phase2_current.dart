// Chrome Web MVP Navigation
// ignore_for_file: avoid_web_libraries_in_flutter, deprecated_member_use

import 'dart:async';
import 'dart:html' as html;

import 'package:flutter/material.dart';
import 'package:flutter_map/flutter_map.dart';
import 'package:latlong2/latlong.dart';

import '../models/commute_plan.dart';
import '../services/flow_backend_api_service.dart';
import '../theme/flow_theme.dart';

class RealRouteNavigationPanel extends StatefulWidget {
  const RealRouteNavigationPanel({
    super.key,
    required this.plan,
  });

  final CommutePlan plan;

  @override
  State<RealRouteNavigationPanel> createState() =>
      _RealRouteNavigationPanelState();
}

class _RealRouteNavigationPanelState extends State<RealRouteNavigationPanel> {
  late final FlowBackendApiService _api;

  bool _loading = false;
  String? _routeError;
  List<Map<String, dynamic>> _routes = const [];
  String? _selectedCandidateId;

  String? _navigationSessionId;
  Map<String, dynamic>? _navigationState;
  String? _navigationError;
  bool _startingNavigation = false;

  Timer? _gpsTimer;
  bool _gpsRunning = false;
  bool _readingGps = false;
  bool _sendingGps = false;
  double? _gpsLat;
  double? _gpsLon;
  double? _gpsAccuracy;
  String _gpsStatus = 'GPS 대기 중';

  String? _lastPlanKey;

  @override
  void initState() {
    super.initState();
    _api = FlowBackendApiService(
      baseUri: Uri.parse('http://127.0.0.1:8000'),
    );
    WidgetsBinding.instance.addPostFrameCallback((_) => _ensureLoaded());
  }

  @override
  void didUpdateWidget(covariant RealRouteNavigationPanel oldWidget) {
    super.didUpdateWidget(oldWidget);
    WidgetsBinding.instance.addPostFrameCallback((_) => _ensureLoaded());
  }

  @override
  void dispose() {
    _gpsTimer?.cancel();
    _api.close();
    super.dispose();
  }

  String _planKey(CommutePlan plan) {
    final o = plan.originPlace;
    final d = plan.destinationPlace;
    return '${o?.tmapPoiId}|${o?.latitude}|${o?.longitude}|'
        '${d?.tmapPoiId}|${d?.latitude}|${d?.longitude}';
  }

  bool get _canLoad =>
      widget.plan.transport == TransportMode.car &&
      widget.plan.originPlace?.latitude != null &&
      widget.plan.originPlace?.longitude != null &&
      widget.plan.destinationPlace?.latitude != null &&
      widget.plan.destinationPlace?.longitude != null;

  Future<void> _ensureLoaded() async {
    if (!mounted || !_canLoad) return;
    final key = _planKey(widget.plan);
    if (_lastPlanKey == key && (_loading || _routes.isNotEmpty)) return;
    _lastPlanKey = key;
    await _loadRoutes();
  }

  Future<void> _loadRoutes({bool forceRefresh = false}) async {
    final origin = widget.plan.originPlace;
    final destination = widget.plan.destinationPlace;
    if (origin == null || destination == null) return;

    _resetNavigation();
    setState(() {
      _loading = true;
      _routeError = null;
      _routes = const [];
      _selectedCandidateId = null;
    });

    try {
      final response = await _api.generateRoutes(
        origin: origin,
        destination: destination,
        forceRefresh: forceRefresh,
      );
      final routes = _extractRoutes(response);
      if (routes.isEmpty) {
        throw StateError('사용 가능한 실제 TMAP Route가 없습니다.');
      }

      Map<String, dynamic> first = routes.first;
      for (final route in routes) {
        final geometry = route['geometry'];
        if (route['is_usable'] != false && geometry is List && geometry.isNotEmpty) {
          first = route;
          break;
        }
      }

      if (!mounted) return;
      setState(() {
        _routes = routes;
        _selectedCandidateId = _candidateId(first);
      });
    } catch (error) {
      if (!mounted) return;
      setState(() => _routeError = '$error');
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  List<Map<String, dynamic>> _extractRoutes(Map<String, dynamic> response) {
    dynamic raw = response['routes'];
    if (raw is! List && response['data'] is Map) {
      raw = (response['data'] as Map)['routes'];
    }
    if (raw is! List) return const [];
    return raw
        .whereType<Map>()
        .map((item) => Map<String, dynamic>.from(item))
        .toList(growable: false);
  }

  String _candidateId(Map<String, dynamic> route) =>
      route['candidate_id']?.toString().toUpperCase() ?? '?';

  Map<String, dynamic>? get _selectedRoute {
    final id = _selectedCandidateId;
    if (id == null) return null;
    for (final route in _routes) {
      if (_candidateId(route) == id) return route;
    }
    return null;
  }

  void _selectRoute(String id) {
    if (_selectedCandidateId == id) return;
    _resetNavigation();
    setState(() => _selectedCandidateId = id);
  }

  void _resetNavigation() {
    _gpsTimer?.cancel();
    _gpsTimer = null;
    _gpsRunning = false;
    _readingGps = false;
    _sendingGps = false;
    _navigationSessionId = null;
    _navigationState = null;
    _navigationError = null;
    _gpsLat = null;
    _gpsLon = null;
    _gpsAccuracy = null;
    _gpsStatus = 'GPS 대기 중';
  }

  Future<Map<String, dynamic>> _routeForNavigation() async {
    var route = _selectedRoute;
    if (route == null) throw StateError('선택된 Route가 없습니다.');

    final guidance = route['navigation_guidance'];
    final geometry = route['geometry'];
    if (guidance is List && guidance.isNotEmpty && geometry is List && geometry.isNotEmpty) {
      return route;
    }

    final origin = widget.plan.originPlace!;
    final destination = widget.plan.destinationPlace!;
    final candidateId = _selectedCandidateId!;
    final response = await _api.generateRoutes(
      origin: origin,
      destination: destination,
      forceRefresh: true,
    );
    final refreshed = _extractRoutes(response);
    for (final item in refreshed) {
      if (_candidateId(item) == candidateId) {
        route = item;
        break;
      }
    }

    if (route == null || route['navigation_guidance'] is! List ||
        (route['navigation_guidance'] as List).isEmpty) {
      throw StateError('Navigation Guidance를 준비하지 못했습니다.');
    }

    if (mounted) setState(() => _routes = refreshed);
    return route;
  }

  Future<void> _startNavigation() async {
    if (_startingNavigation) return;
    setState(() {
      _startingNavigation = true;
      _navigationError = null;
      _gpsStatus = 'Navigation Route 준비 중...';
    });

    try {
      final route = await _routeForNavigation();
      final result = await _api.startNavigation(route: route);
      final sessionId = result['session_id']?.toString();
      if (sessionId == null || sessionId.isEmpty) {
        throw StateError('Navigation session_id가 없습니다.');
      }
      if (!mounted) return;
      setState(() {
        _navigationSessionId = sessionId;
        _gpsStatus = 'Browser GPS 연결 준비 중...';
      });
      await _startGps();
    } catch (error) {
      if (!mounted) return;
      setState(() {
        _navigationError = '$error';
        _gpsStatus = '내비게이션 시작 실패';
      });
    } finally {
      if (mounted) setState(() => _startingNavigation = false);
    }
  }

  Future<Map<String, double>> _browserPosition() async {
    final position = await html.window.navigator.geolocation.getCurrentPosition(
      enableHighAccuracy: true,
    );
    final coords = position.coords;
    if (coords == null) throw StateError('브라우저 GPS 좌표가 없습니다.');
    final lat = coords.latitude?.toDouble();
    final lon = coords.longitude?.toDouble();
    final accuracy = coords.accuracy?.toDouble();
    if (lat == null || lon == null || accuracy == null) {
      throw StateError('브라우저 GPS 값을 읽을 수 없습니다.');
    }
    return {'lat': lat, 'lon': lon, 'accuracy': accuracy};
  }

  Future<void> _pollGps() async {
    if (_readingGps || _navigationSessionId == null) return;
    _readingGps = true;
    try {
      final p = await _browserPosition();
      await _sendGps(p['lat']!, p['lon']!, p['accuracy']!);
    } catch (error) {
      if (mounted) setState(() => _gpsStatus = 'Browser GPS 오류: $error');
    } finally {
      _readingGps = false;
    }
  }

  Future<void> _sendGps(double lat, double lon, double accuracy) async {
    final session = _navigationSessionId;
    if (session == null || _sendingGps) return;
    _sendingGps = true;
    try {
      final state = await _api.updateNavigation(
        sessionId: session,
        currentLat: lat,
        currentLon: lon,
      );
      final status = state['status']?.toString();
      if (status == 'ARRIVING') {
        _gpsTimer?.cancel();
        _gpsTimer = null;
      }
      if (!mounted) return;
      setState(() {
        _gpsLat = lat;
        _gpsLon = lon;
        _gpsAccuracy = accuracy;
        _navigationState = state;
        _navigationError = null;
        if (status == 'ARRIVING') {
          _gpsRunning = false;
          _gpsStatus = '목적지 도착 · GPS 자동 종료';
        } else {
          _gpsStatus = 'Browser GPS 수신 중 · '
              '${lat.toStringAsFixed(6)}, ${lon.toStringAsFixed(6)}';
        }
      });
    } catch (error) {
      final text = '$error';
      if (text.contains('404')) {
        _gpsTimer?.cancel();
        _gpsTimer = null;
      }
      if (!mounted) return;
      setState(() {
        if (text.contains('404')) {
          _gpsRunning = false;
          _gpsStatus = 'Navigation 세션 만료 · GPS 자동 종료';
          _navigationError = 'FastAPI가 재시작되었다면 내비게이션을 다시 시작해주세요.';
        } else {
          _gpsStatus = 'GPS 전송 실패';
          _navigationError = text;
        }
      });
    } finally {
      _sendingGps = false;
    }
  }

  Future<void> _startGps() async {
    _gpsTimer?.cancel();
    _gpsTimer = null;
    if (mounted) setState(() => _gpsStatus = '브라우저 위치 확인 중...');
    await _pollGps();
    if (_navigationState?['status']?.toString() == 'ARRIVING') return;
    _gpsTimer = Timer.periodic(const Duration(seconds: 1), (_) => _pollGps());
    if (mounted) setState(() => _gpsRunning = true);
  }

  void _stopGps() {
    _gpsTimer?.cancel();
    _gpsTimer = null;
    if (mounted) {
      setState(() {
        _gpsRunning = false;
        _gpsStatus = 'GPS 중지됨';
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    if (!_canLoad) {
      return _InfoCard(
        icon: Icons.location_off_outlined,
        title: '실제 경로를 만들려면 장소를 선택해주세요.',
        description: '출발지와 목적지를 TMAP 검색 결과에서 선택해야 정확한 좌표를 사용할 수 있어요.',
      );
    }

    if (_loading) {
      return const _InfoCard(
        icon: Icons.route_outlined,
        title: '실제 TMAP A/B/C를 만들고 있어요.',
        description: 'TMAP → MOCT_LINK → 성남 분류 → AI Coverage를 처리 중입니다.',
        loading: true,
      );
    }

    if (_routeError != null) {
      return _ErrorCard(error: _routeError!, onRetry: () => _loadRoutes());
    }

    final route = _selectedRoute;
    if (route == null) {
      return const _InfoCard(
        icon: Icons.route_outlined,
        title: '표시할 실제 경로가 없습니다.',
        description: 'Route 생성 결과를 확인해주세요.',
      );
    }

    return Container(
      width: double.infinity,
      padding: const EdgeInsets.all(22),
      decoration: BoxDecoration(
        color: Colors.white,
        borderRadius: BorderRadius.circular(20),
        border: Border.all(color: FlowColors.border),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              const Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      '실제 TMAP 경로',
                      style: TextStyle(fontSize: 20, fontWeight: FontWeight.w800),
                    ),
                    SizedBox(height: 4),
                    Text(
                      '실제 TMAP·MOCT_LINK 결과입니다. AI 미래예측·최종 추천과는 아직 분리되어 있습니다.',
                      style: TextStyle(fontSize: 12, color: FlowColors.textSecondary),
                    ),
                  ],
                ),
              ),
              IconButton(
                tooltip: '실제 경로 새로고침',
                onPressed: () => _loadRoutes(forceRefresh: true),
                icon: const Icon(Icons.refresh),
              ),
            ],
          ),
          const SizedBox(height: 16),
          SingleChildScrollView(
            scrollDirection: Axis.horizontal,
            child: SegmentedButton<String>(
              segments: [
                for (final item in _routes)
                  ButtonSegment<String>(
                    value: _candidateId(item),
                    icon: const Icon(Icons.alt_route),
                    label: Text(_routeButtonLabel(item)),
                  ),
              ],
              selected: {_selectedCandidateId!},
              showSelectedIcon: false,
              onSelectionChanged: (values) => _selectRoute(values.first),
            ),
          ),
          const SizedBox(height: 16),
          _RouteMetrics(route: route),
          const SizedBox(height: 16),
          SizedBox(
            height: 430,
            child: Stack(
              children: [
                Positioned.fill(
                  child: _SelectedRouteMap(
                    route: route,
                    plan: widget.plan,
                  ),
                ),
                _NavigationBanner(state: _navigationState),
              ],
            ),
          ),
          const SizedBox(height: 16),
          _buildNavigationCard(),
        ],
      ),
    );
  }

  String _routeButtonLabel(Map<String, dynamic> route) {
    final id = _candidateId(route);
    final distance = _num(route['total_distance_m']);
    final eta = _num(route['tmap_eta_min']) ??
        ((_num(route['tmap_eta_sec']) ?? 0) / 60.0);
    final bits = <String>['Route $id'];
    if (distance != null) bits.add('${(distance / 1000).toStringAsFixed(1)}km');
    if (eta > 0) bits.add('${eta.toStringAsFixed(1)}분');
    return bits.join('\n');
  }

  Widget _buildNavigationCard() {
    final state = _navigationState;
    final status = state?['status']?.toString() ??
        (_navigationSessionId == null ? '-' : 'GPS_WAITING');
    final primary = state?['primary_text']?.toString() ?? '';
    final secondary = state?['secondary_text']?.toString() ?? '';
    final arrived = status == 'ARRIVING';

    return Container(
      width: double.infinity,
      padding: const EdgeInsets.all(18),
      decoration: BoxDecoration(
        color: const Color(0xFFFAFBFC),
        borderRadius: BorderRadius.circular(14),
        border: Border.all(color: FlowColors.border),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              const Icon(Icons.navigation_outlined, color: FlowColors.primary),
              const SizedBox(width: 8),
              const Expanded(
                child: Text('실제 턴바이턴 내비게이션',
                    style: TextStyle(fontWeight: FontWeight.w800)),
              ),
              FilledButton.icon(
                onPressed: _startingNavigation || _navigationSessionId != null
                    ? null
                    : _startNavigation,
                icon: _startingNavigation
                    ? const SizedBox(
                        width: 16,
                        height: 16,
                        child: CircularProgressIndicator(strokeWidth: 2),
                      )
                    : Icon(arrived ? Icons.flag : Icons.play_arrow),
                label: Text(_startingNavigation
                    ? '준비 중...'
                    : arrived
                        ? '도착 완료'
                        : _navigationSessionId != null
                            ? '안내 중'
                            : '내비게이션 시작'),
              ),
            ],
          ),
          if (primary.isNotEmpty) ...[
            const SizedBox(height: 14),
            Text(primary,
                style: const TextStyle(fontSize: 20, fontWeight: FontWeight.w800)),
            if (secondary.isNotEmpty) ...[
              const SizedBox(height: 3),
              Text(secondary,
                  style: const TextStyle(color: FlowColors.textSecondary)),
            ],
          ],
          const SizedBox(height: 10),
          Text('상태: $status',
              style: const TextStyle(fontSize: 12, color: FlowColors.textSecondary)),
          const SizedBox(height: 4),
          Text(_gpsStatus,
              style: const TextStyle(fontSize: 12, color: FlowColors.textSecondary)),
          if (_gpsLat != null && _gpsLon != null) ...[
            const SizedBox(height: 3),
            Text(
              'GPS ${_gpsLat!.toStringAsFixed(6)}, ${_gpsLon!.toStringAsFixed(6)}'
              '${_gpsAccuracy == null ? '' : ' · ±${_gpsAccuracy!.toStringAsFixed(0)}m'}',
              style: const TextStyle(fontSize: 11, color: FlowColors.textTertiary),
            ),
          ],
          if (_navigationSessionId != null && !arrived) ...[
            const SizedBox(height: 10),
            OutlinedButton.icon(
              onPressed: _gpsRunning ? _stopGps : _startGps,
              icon: Icon(_gpsRunning ? Icons.location_off : Icons.my_location),
              label: Text(_gpsRunning ? 'GPS 중지' : 'GPS 다시 시작'),
            ),
          ],
          if (_navigationError != null) ...[
            const SizedBox(height: 10),
            Text(_navigationError!,
                style: const TextStyle(fontSize: 12, color: Colors.red)),
          ],
        ],
      ),
    );
  }
}

class _SelectedRouteMap extends StatelessWidget {
  const _SelectedRouteMap({required this.route, required this.plan});

  final Map<String, dynamic> route;
  final CommutePlan plan;

  @override
  Widget build(BuildContext context) {
    final raw = route['geometry'];
    final points = <LatLng>[];
    if (raw is List) {
      for (final item in raw) {
        if (item is List && item.length >= 2 && item[0] is num && item[1] is num) {
          points.add(LatLng((item[1] as num).toDouble(), (item[0] as num).toDouble()));
        }
      }
    }
    if (points.isEmpty) return const Center(child: Text('Geometry가 없습니다.'));

    final markers = <Marker>[];
    final origin = plan.originPlace;
    final destination = plan.destinationPlace;
    if (origin?.latitude != null && origin?.longitude != null) {
      markers.add(Marker(
        point: LatLng(origin!.latitude!, origin.longitude!),
        width: 44,
        height: 44,
        child: const Icon(Icons.trip_origin, size: 30, color: Color(0xFF2563EB)),
      ));
    }
    if (destination?.latitude != null && destination?.longitude != null) {
      markers.add(Marker(
        point: LatLng(destination!.latitude!, destination.longitude!),
        width: 44,
        height: 44,
        child: const Icon(Icons.location_on, size: 36, color: Color(0xFFDC2626)),
      ));
    }

    return ClipRRect(
      borderRadius: BorderRadius.circular(16),
      child: FlutterMap(
        key: ValueKey('${route['route_id']}-${points.length}'),
        options: MapOptions(
          initialCameraFit: CameraFit.bounds(
            bounds: LatLngBounds.fromPoints(points),
            padding: const EdgeInsets.all(44),
          ),
        ),
        children: [
          TileLayer(
            urlTemplate: 'https://tile.openstreetmap.org/{z}/{x}/{y}.png',
            userAgentPackageName: 'flow_app',
          ),
          PolylineLayer(polylines: [
            Polyline(points: points, strokeWidth: 6, color: FlowColors.primary),
          ]),
          if (markers.isNotEmpty) MarkerLayer(markers: markers),
          RichAttributionWidget(
            attributions: [TextSourceAttribution('OpenStreetMap contributors')],
          ),
        ],
      ),
    );
  }
}

class _RouteMetrics extends StatelessWidget {
  const _RouteMetrics({required this.route});
  final Map<String, dynamic> route;

  @override
  Widget build(BuildContext context) {
    final distance = _num(route['total_distance_m']);
    final eta = _num(route['tmap_eta_min']) ??
        ((_num(route['tmap_eta_sec']) ?? 0) / 60.0);

    final metrics = <(String, String)>[
      ('경로', 'Route ${route['candidate_id'] ?? '-'} · ${_routeLabel(route['route_label'])}'),
      ('거리', distance == null ? '-' : '${(distance / 1000).toStringAsFixed(2)} km'),
      ('TMAP ETA', eta <= 0 ? '-' : '${eta.toStringAsFixed(1)}분'),
      ('Mapping', route['mapping_quality']?.toString() ?? '-'),
      ('Coverage', _percent(route['mapping_coverage_percent'])),
      ('성남 구간', _percent(route['seongnam_distance_ratio_percent'])),
      ('Matched LINK', route['matched_link_count']?.toString() ?? '-'),
      ('AI LINK Coverage', _percent(route['ai_link_coverage_percent'])),
    ];

    return Wrap(
      spacing: 10,
      runSpacing: 10,
      children: [
        for (final item in metrics)
          Container(
            width: 125,
            padding: const EdgeInsets.all(11),
            decoration: BoxDecoration(
              color: const Color(0xFFFAFBFC),
              borderRadius: BorderRadius.circular(12),
              border: Border.all(color: FlowColors.border),
            ),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(item.$1,
                    style: const TextStyle(fontSize: 11, color: FlowColors.textSecondary)),
                const SizedBox(height: 4),
                Text(item.$2,
                    maxLines: 2,
                    overflow: TextOverflow.ellipsis,
                    style: const TextStyle(fontSize: 13, fontWeight: FontWeight.w700)),
              ],
            ),
          ),
      ],
    );
  }
}

class _NavigationBanner extends StatelessWidget {
  const _NavigationBanner({required this.state});
  final Map<String, dynamic>? state;

  @override
  Widget build(BuildContext context) {
    final text = state?['primary_text']?.toString() ?? '';
    if (text.isEmpty) return const SizedBox.shrink();
    final secondary = state?['secondary_text']?.toString() ?? '';
    return Positioned(
      left: 12,
      right: 12,
      top: 12,
      child: Material(
        elevation: 4,
        borderRadius: BorderRadius.circular(14),
        child: Padding(
          padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 14),
          child: Row(
            children: [
              const Icon(Icons.navigation, color: FlowColors.primary),
              const SizedBox(width: 10),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(text,
                        style: const TextStyle(fontSize: 18, fontWeight: FontWeight.w800)),
                    if (secondary.isNotEmpty)
                      Text(secondary,
                          style: const TextStyle(fontSize: 12, color: FlowColors.textSecondary)),
                  ],
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

class _InfoCard extends StatelessWidget {
  const _InfoCard({
    required this.icon,
    required this.title,
    required this.description,
    this.loading = false,
  });

  final IconData icon;
  final String title;
  final String description;
  final bool loading;

  @override
  Widget build(BuildContext context) {
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.all(18),
      decoration: BoxDecoration(
        color: Colors.white,
        borderRadius: BorderRadius.circular(14),
        border: Border.all(color: FlowColors.border),
      ),
      child: Row(
        children: [
          if (loading)
            const SizedBox(width: 22, height: 22, child: CircularProgressIndicator(strokeWidth: 2))
          else
            Icon(icon, color: FlowColors.primary),
          const SizedBox(width: 12),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(title, style: const TextStyle(fontWeight: FontWeight.w800)),
                const SizedBox(height: 3),
                Text(description,
                    style: const TextStyle(fontSize: 12, color: FlowColors.textSecondary)),
              ],
            ),
          ),
        ],
      ),
    );
  }
}

class _ErrorCard extends StatelessWidget {
  const _ErrorCard({required this.error, required this.onRetry});
  final String error;
  final VoidCallback onRetry;

  @override
  Widget build(BuildContext context) {
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.all(18),
      decoration: BoxDecoration(
        color: const Color(0xFFFFFBEB),
        borderRadius: BorderRadius.circular(14),
        border: Border.all(color: const Color(0xFFFDE68A)),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const Text('실제 경로를 불러오지 못했습니다.',
              style: TextStyle(fontWeight: FontWeight.w800)),
          const SizedBox(height: 6),
          SelectableText(error, style: const TextStyle(fontSize: 12)),
          const SizedBox(height: 10),
          OutlinedButton(onPressed: onRetry, child: const Text('다시 시도')),
        ],
      ),
    );
  }
}

double? _num(dynamic value) {
  if (value is num) return value.toDouble();
  return double.tryParse(value?.toString() ?? '');
}

String _percent(dynamic value) {
  final n = _num(value);
  return n == null ? '-' : '${n.toStringAsFixed(1)}%';
}

String _routeLabel(dynamic value) {
  return switch (value?.toString()) {
    'traffic_optimal' => '교통 최적',
    'minimum_time' => '최소 시간',
    'shortest' => '최단 거리',
    final String text when text.isNotEmpty => text,
    _ => '-',
  };
}
