from collections import Counter

from backend.services.route_engine import request_tmap_route


origin = {
    "name": "판교역",
    "lat": 37.395893,
    "lon": 127.111236,
}

destination = {
    "name": "강남역",
    "lat": 37.497175,
    "lon": 127.027926,
}


print()
print("========================================")
print("PHASE 2 TMAP Traffic Test")
print("========================================")
print()


route = request_tmap_route(
    origin=origin,
    destination=destination,
    candidate_id="A",
)


segments = route.get(
    "traffic_segments",
    [],
)


print("Candidate:", route.get("candidate_id"))
print("Distance:", route.get("total_distance_m"), "m")
print("ETA:", route.get("tmap_eta_min"), "min")
print("Geometry:", route.get("geometry_point_count"))
print("Navigation:", route.get("navigation_guidance_count"))
print("Traffic segments:", route.get("traffic_segment_count"))
print()


levels = Counter(
    segment.get("congestion_level")
    for segment in segments
)


print("Traffic level counts:")
print(levels)
print()


print("Sample:")
for segment in segments[:10]:

    print(
        "seq=",
        segment.get("sequence"),
        "| road=",
        segment.get("road_name"),
        "| level=",
        segment.get("congestion_level"),
        "| label=",
        segment.get("congestion_label"),
        "| speed=",
        segment.get("speed_kmh"),
        "| points=",
        len(
            segment.get(
                "geometry",
                [],
            )
        ),
    )
