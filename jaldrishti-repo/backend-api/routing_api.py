"""
JalDrishti flood-aware routing API.

This file:
1. Loads real Koramangala road data from OpenStreetMap using OSMnx.
2. Loads real predicted flood-risk data from risk_lookup_koramangala.json.
3. Matches each risk segment to nearby OSM road edges.
4. Uses custom Dijkstra from routing.py.
5. Returns GeoJSON for the Leaflet frontend dashboard.

Run from backend-api folder:
    python -m uvicorn routing_api:app --reload

Open:
    http://127.0.0.1:8000/docs
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


# ---------------------------------------------------------------------------
# Real OSM road graph
# ---------------------------------------------------------------------------

def get_graph():
    """
    Loads the real Koramangala driving-road graph once.

    The graph stays in memory while the server is running, so the map data
    is not downloaded again on every dashboard request.
    """
    if _state["graph"] is None:
        print(
            f"Loading OpenStreetMap road graph for {PLACE_NAME}..."
        )

        _state["graph"] = load_osm_graph(
            PLACE_NAME
        )

        print("Road graph loaded and cached.")

    return _state["graph"]


# ---------------------------------------------------------------------------
# Real flood-risk lookup data
# ---------------------------------------------------------------------------

def load_risk_data():
    """
    Load the JSON output from Pair 1.

    Required JSON format:

    {
      "ward_id": "koramangala",
      "generated_at": "...",
      "timesteps": {
        "2026-09-07T15:00:00": [
          {
            "segment_id": "seg_0001",
            "geometry": [[longitude, latitude], ...],
            "risk_score": 0.39,
            "predicted_depth_cm": 11.7,
            "confidence": 0.6
          }
        ]
      }
    }
    """
    if _state["risk_data"] is not None:
        return _state["risk_data"]

    if not os.path.exists(RISK_LOOKUP_PATH):
        raise FileNotFoundError(
            "risk_lookup_koramangala.json was not found "
            "in the backend-api folder."
        )

    with open(
        RISK_LOOKUP_PATH,
        "r",
        encoding="utf-8",
    ) as file:
        _state["risk_data"] = json.load(file)

    timestep_count = len(
        _state["risk_data"].get(
            "timesteps",
            {},
        )
    )

    print(
        f"Loaded real flood-risk data with "
        f"{timestep_count} timesteps."
    )

    return _state["risk_data"]


def segment_midpoint(geometry):
    """
    Convert risk-segment geometry into a midpoint.

    Input geometry:
    [
        [longitude, latitude],
        [longitude, latitude],
        ...
    ]

    Return:
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
    Return the flood-risk segments for a selected forecast timestamp.

    If timestep is missing or invalid, use the first timestamp available.

    Return:
        segments, timestamp_used
    """
    risk_data = load_risk_data()

    timesteps = risk_data.get(
        "timesteps",
        {},
    )

    if not timesteps:
        return [], None

    if timestep and timestep in timesteps:
        return (
            timesteps[timestep],
            timestep,
        )

    first_timestamp = next(iter(timesteps))

    return (
        timesteps[first_timestamp],
        first_timestamp,
    )


# ---------------------------------------------------------------------------
# Apply risk scores to real OSM road edges
# ---------------------------------------------------------------------------

def apply_risk_to_graph(graph, timestep=None):
    """
    Add flood-risk scores to real OSM road edges.

    Pair 1's risk JSON contains road geometry and segment IDs. OSM has its own
    graph node/edge IDs. For the prototype, each OSM edge is assigned the
    risk score from the geographically closest risk segment.

    Return:
        graph, timestep_used
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


# ---------------------------------------------------------------------------
# GeoJSON conversion helpers
# ---------------------------------------------------------------------------

def path_to_geojson_feature(path, properties=None):
    """
    Turn a path into a GeoJSON LineString Feature.

    Path input:
    [
        [longitude, latitude],
        ...
    ]
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
    timestep=None,
    risk_threshold=0.55,
):
    """
    Return source segment IDs whose predicted risk is severe enough
    to be treated as unsafe for the safe route.
    """
    segments, _ = get_segments_for_timestep(
        timestep
    )

    return [
        segment.get("segment_id", "unknown")
        for segment in segments
        if float(
            segment.get("risk_score", 0.0)
        ) >= risk_threshold
    ]


# ---------------------------------------------------------------------------
# API endpoints
# ---------------------------------------------------------------------------

@app.get("/")
def root():
    """
    Shows API health and confirms whether real flood-risk data is loaded.
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
            risk_data.get(
                "timesteps",
                {},
            ).keys()
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
    Return shortest and flood-safe routes for the Leaflet dashboard.

    The returned GeoJSON FeatureCollection contains:

    - shortest:
      Real OSM route based only on road distance.
      Frontend should draw this as blue and dashed.

    - safe:
      Real OSM route calculated through custom Dijkstra.
      Flood-risk edges are heavily penalized or blocked.
      Frontend should draw this as green and solid.
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

    risk_data = load_risk_data()

    return {
        "type": "FeatureCollection",
        "features": features,
        "meta": {
            "ward_id": risk_data.get(
                "ward_id",
                "koramangala",
            ),
            "timestep_used": timestep_used,
            "using_real_risk_data": bool(
                risk_data.get("timesteps")
            ),
            "risk_penalty_applied": True,
            "risk_penalty_factor": 15.0,
            "risk_threshold": 0.55,
            "avoided_segments": get_severe_risk_segments(
                timestep=timestep_used,
                risk_threshold=0.55,
            ),
            "algorithm": "Custom Dijkstra",
        },
    }
