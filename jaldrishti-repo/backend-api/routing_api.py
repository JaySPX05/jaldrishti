"""
FastAPI wrapper for JalDrishti flood-aware routing.

It:
1. Loads real Koramangala roads from OpenStreetMap.
2. Loads flood risk data from risk_lookup_koramangala.json.
3. Assigns flood-risk scores to nearby road edges.
4. Calls custom Dijkstra in routing.py.
5. Returns GeoJSON for the Leaflet dashboard.

Run:
    python -m uvicorn routing_api:app --reload
"""

import json
import os

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from routing import compute_route, load_osm_graph

app = FastAPI(
    title="JalDrishti Routing API",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

PLACE_NAME = "Koramangala, Bengaluru, India"

RISK_LOOKUP_PATH = os.path.join(
    os.path.dirname(__file__),
    "risk_lookup_koramangala.json",
)

_state = {
    "graph": None,
    "risk_data": None,
}


def get_graph():
    """
    Load the real OSM road graph once, then cache it in memory.
    """
    if _state["graph"] is None:
        print(
            f"Loading real OSM roads for {PLACE_NAME}..."
        )

        _state["graph"] = load_osm_graph(
            PLACE_NAME
        )

    return _state["graph"]


def load_risk_data():
    """
    Load the real risk lookup file.

    Expected data shape:

    {
      "ward_id": "koramangala",
      "generated_at": "...",
      "timesteps": {
        "2026-09-07T15:00:00": [
          {
            "segment_id": "seg_0001",
            "geometry": [[longitude, latitude], ...],
            "risk_score": 0.39
          }
        ]
      }
    }
    """
    if _state["risk_data"] is not None:
        return _state["risk_data"]

    if not os.path.exists(RISK_LOOKUP_PATH):
        raise FileNotFoundError(
            "Could not find risk_lookup_koramangala.json "
            "in backend-api."
        )

    with open(
        RISK_LOOKUP_PATH,
        "r",
        encoding="utf-8",
    ) as file:
        _state["risk_data"] = json.load(file)

    print(
        "Loaded risk data with "
        f"{len(_state['risk_data'].get('timesteps', {}))} "
        "timesteps."
    )

    return _state["risk_data"]


def segment_midpoint(geometry):
    """
    Convert segment geometry from:
    [[longitude, latitude], ...]

    into:
    (latitude, longitude)
    """
    longitudes = [
        point[0]
        for point in geometry
    ]

    latitudes = [
        point[1]
        for point in geometry
    ]

    return (
        sum(latitudes) / len(latitudes),
        sum(longitudes) / len(longitudes),
    )


def get_segments_for_timestep(timestep=None):
    """
    Return risk segments and the timestamp that was actually used.

    If no valid timestamp is supplied, the first available time is used.
    """
    risk_data = load_risk_data()

    timesteps = risk_data.get(
        "timesteps",
        {},
    )

    if not timesteps:
        return [], None

    if timestep in timesteps:
        return timesteps[timestep], timestep

    first_timestamp = next(iter(timesteps))

    return (
        timesteps[first_timestamp],
        first_timestamp,
    )


def apply_risk_to_graph(graph, timestep=None):
    """
    Set edge_data["risk_score"] for every OSM road edge.

    For this prototype, each road edge receives the risk score from the
    geographically closest Pair 1 predicted segment.
    """
    segments, timestep_used = get_segments_for_timestep(
        timestep
    )

    for _, _, _, edge_data in graph.edges(
        keys=True,
        data=True,
    ):
        edge_data["risk_score"] = 0.0

    if not segments:
        return graph, timestep_used

    usable_segments = [
        segment
        for segment in segments
        if segment.get("geometry")
    ]

    if not usable_segments:
        return graph, timestep_used

    segment_points = [
        segment_midpoint(segment["geometry"])
        for segment in usable_segments
    ]

    segment_risks = [
        float(segment.get("risk_score", 0.0))
        for segment in usable_segments
    ]

    for source, destination, _, edge_data in graph.edges(
        keys=True,
        data=True,
    ):
        edge_latitude = (
            graph.nodes[source]["y"]
            + graph.nodes[destination]["y"]
        ) / 2

        edge_longitude = (
            graph.nodes[source]["x"]
            + graph.nodes[destination]["x"]
        ) / 2

        nearest_distance = float("inf")
        nearest_risk = 0.0

        for (
            segment_latitude,
            segment_longitude,
        ), risk_score in zip(
            segment_points,
            segment_risks,
        ):
            distance = (
                (edge_latitude - segment_latitude) ** 2
                + (edge_longitude - segment_longitude) ** 2
            )

            if distance < nearest_distance:
                nearest_distance = distance
                nearest_risk = risk_score

        edge_data["risk_score"] = nearest_risk

    return graph, timestep_used


def path_to_geojson_feature(
    path,
    properties=None,
):
    """
    Convert [[longitude, latitude], ...] to GeoJSON LineString.
    """
    if not path:
        return None

    return {
        "type": "Feature",
        "properties": properties or {},
        "geometry": {
            "type": "LineString",
            "coordinates": path,
        },
    }


def get_severe_risk_segments(
    timestep,
    risk_threshold=0.55,
):
    """
    Return Pair 1 segment IDs treated as unsafe for this route.
    """
    segments, _ = get_segments_for_timestep(
        timestep
    )

    return [
        segment.get("segment_id", "unknown")
        for segment in segments
        if float(segment.get("risk_score", 0.0))
        >= risk_threshold
    ]


@app.get("/")
def root():
    """
    Health check plus routing-data status.
    """
    risk_data = load_risk_data()

    return {
        "status": "ok",
        "ward_id": risk_data.get(
            "ward_id",
            "koramangala",
        ),
        "using_real_risk_data": bool(
            risk_data.get("timesteps")
        ),
        "available_timesteps": list(
            risk_data.get("timesteps", {}).keys()
        ),
    }


@app.get("/route")
def route(
    start_lat: float,
    start_lon: float,
    end_lat: float,
    end_lon: float,
    timestep: str = None,
):
    """
    Return a GeoJSON FeatureCollection for Leaflet.

    The response contains:
    - shortest: route that ignores flood risk
    - safe: route calculated with flood-risk penalties
    """
    graph = get_graph()

    graph, timestep_used = apply_risk_to_graph(
        graph,
        timestep=timestep,
    )

    shortest_result = compute_route(
        G=graph,
        from_lng=start_lon,
        from_lat=start_lat,
        to_lng=end_lon,
        to_lat=end_lat,
        risk_penalty_factor=0.0,
        risk_threshold=1.1,
    )

    safe_result = compute_route(
        G=graph,
        from_lng=start_lon,
        from_lat=start_lat,
        to_lng=end_lon,
        to_lat=end_lat,
        risk_penalty_factor=15.0,
        risk_threshold=0.55,
    )

    if not shortest_result["path"] and not safe_result["path"]:
        raise HTTPException(
            status_code=404,
            detail="No route found between these points.",
        )

    features = []

    shortest_feature = path_to_geojson_feature(
        shortest_result["path"],
        properties={
            "route_type": "shortest",
            "color": "#2563eb",
            "route_cost": shortest_result[
                "route_cost"
            ],
        },
    )

    safe_feature = path_to_geojson_feature(
        safe_result["path"],
        properties={
            "route_type": "safe",
            "color": "#16a34a",
            "route_cost": safe_result[
                "route_cost"
            ],
        },
    )

    if shortest_feature:
        features.append(shortest_feature)

    if safe_feature:
        features.append(safe_feature)

    return {
        "type": "FeatureCollection",
        "features": features,
        "meta": {
            "ward_id": "koramangala",
            "timestep_used": timestep_used,
            "risk_penalty_applied": True,
            "risk_threshold": 0.55,
            "avoided_segments": get_severe_risk_segments(
                timestep=timestep_used,
                risk_threshold=0.55,
            ),
            "algorithm": "Custom Dijkstra",
        },
    }
