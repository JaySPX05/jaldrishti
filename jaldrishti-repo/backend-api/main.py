"""
JalDrishti Backend — Risk API + Routing API

Run locally:
    pip install -r requirements.txt
    python -m uvicorn main:app --reload

Then open:
    http://127.0.0.1:8000/docs
"""

from datetime import datetime, timezone
from typing import Optional

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

import mock_data

from mock_data import SYNTHETIC_ROAD_GRAPH
from routing import (
    apply_traffic_to_graph,
    dijkstra,
    get_route_edges,
)
from traffic_service import (
    get_demo_traffic,
    get_live_traffic,
)

app = FastAPI(
    title="JalDrishti Risk API",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# API response models
# ---------------------------------------------------------------------------

class RiskSegment(BaseModel):
    segment_id: str
    geometry: list[list[float]]
    risk_score: float
    predicted_depth_cm: Optional[float] = None
    confidence: Optional[float] = None


class RiskResponse(BaseModel):
    ward_id: str
    timestamp: str
    forecast_window_minutes: int
    segments: list[RiskSegment]


class RouteResponse(BaseModel):
    path: list[list[float]]
    avoided_segments: list[str]
    risk_penalty_applied: bool


# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------

@app.get("/")
def health_check():
    return {
        "status": "ok",
        "service": "jaldrishti-backend",
    }


# ---------------------------------------------------------------------------
# Risk API
# ---------------------------------------------------------------------------

@app.get("/api/v1/risk", response_model=RiskResponse)
def get_risk(
    ward_id: str = Query(
        ...,
        description="Example: koramangala",
    ),
    timestamp: Optional[str] = Query(
        None,
        description="ISO8601. Defaults to current UTC time.",
    ),
):
    """
    Returns flood-risk values for road segments in one ward.

    Currently this reads mock data from mock_data.py.
    Pair 1 can later connect real risk predictions without changing
    this response format.
    """
    ts = timestamp or datetime.now(timezone.utc).isoformat()

    segments = mock_data.get_risk_segments(
        ward_id,
        ts,
    )

    if segments is None:
        raise HTTPException(
            status_code=404,
            detail=(
                f"No data for ward_id='{ward_id}'. "
                f"Known wards: {mock_data.KNOWN_WARDS}"
            ),
        )

    return RiskResponse(
        ward_id=ward_id,
        timestamp=ts,
        forecast_window_minutes=180,
        segments=segments,
    )


# ---------------------------------------------------------------------------
# Frontend route API
# Do not change this response structure without informing the team.
# ---------------------------------------------------------------------------

@app.get("/api/v1/route", response_model=RouteResponse)
def get_route(
    from_lng: float = Query(...),
    from_lat: float = Query(...),
    to_lng: float = Query(...),
    to_lat: float = Query(...),
    ward_id: str = Query(...),
):
    """
    Returns the currently required frontend route shape.

    Right now this gives a direct route line between two points.
    Later, replace this stub with real OSM + Dijkstra routing while
    keeping the RouteResponse structure the same.
    """
    if ward_id not in mock_data.KNOWN_WARDS:
        raise HTTPException(
            status_code=404,
            detail=(
                f"Unknown ward_id='{ward_id}'. "
                f"Known wards: {mock_data.KNOWN_WARDS}"
            ),
        )

    return RouteResponse(
        path=[
            [from_lng, from_lat],
            [to_lng, to_lat],
        ],
        avoided_segments=[],
        risk_penalty_applied=False,
    )


# ---------------------------------------------------------------------------
# Basic Dijkstra demonstration
# ---------------------------------------------------------------------------

@app.get("/api/v1/routing/demo")
def get_routing_demo():
    """
    Calculates the shortest route in the synthetic road graph.

    Expected route:
    A -> C -> B -> D -> E -> F
    """
    route, distance_meters = dijkstra(
        graph=SYNTHETIC_ROAD_GRAPH,
        start="A",
        goal="F",
    )

    return {
        "route_found": route is not None,
        "route": route,
        "route_edges": get_route_edges(route),
        "distance_meters": distance_meters,
        "routing_algorithm": "Dijkstra",
    }


# ---------------------------------------------------------------------------
# Avoided-segment demonstration
# ---------------------------------------------------------------------------

@app.get("/api/v1/routing/avoid-demo")
def get_avoidance_demo():
    """
    Blocks B <-> D and returns a new route.

    In the real project this represents a flooded, unsafe, blocked,
    or closed road segment.
    """
    normal_route, normal_distance = dijkstra(
        graph=SYNTHETIC_ROAD_GRAPH,
        start="A",
        goal="F",
    )

    rerouted_path, rerouted_distance = dijkstra(
        graph=SYNTHETIC_ROAD_GRAPH,
        start="A",
        goal="F",
        blocked_edges={
            ("B", "D"),
            ("D", "B"),
        },
    )

    return {
        "avoided_segment": {
            "from": "B",
            "to": "D",
            "reason": "flood_or_road_closure_demo",
        },
        "normal_route": {
            "path": normal_route,
            "route_edges": get_route_edges(normal_route),
            "distance_meters": normal_distance,
        },
        "rerouted_route": {
            "path": rerouted_path,
            "route_edges": get_route_edges(rerouted_path),
            "distance_meters": rerouted_distance,
        },
        "routing_algorithm": "Dijkstra",
    }


# ---------------------------------------------------------------------------
# Traffic-aware Dijkstra endpoint
# ---------------------------------------------------------------------------

@app.get("/api/v1/routing/live")
def get_live_route():
    """
    Gets live traffic near Koramangala using TomTom if a TOMTOM_API_KEY
    is available in .env.

    If no key is configured, it automatically uses demo traffic data,
    so the endpoint continues to work for a presentation.
    """
    traffic_data = get_live_traffic(
        latitude=12.9352,
        longitude=77.6245,
    )

    if traffic_data is None:
        traffic_data = get_demo_traffic()
    else:
        traffic_data["source"] = "tomtom_live"

    traffic_by_edge = {
        ("B", "D"): traffic_data,
        ("D", "B"): traffic_data,
    }

    traffic_graph = apply_traffic_to_graph(
        graph=SYNTHETIC_ROAD_GRAPH,
        traffic_by_edge=traffic_by_edge,
        default_speed_kmph=35,
    )

    route, travel_time_seconds = dijkstra(
        graph=traffic_graph,
        start="A",
        goal="F",
    )

    if route is None:
        raise HTTPException(
            status_code=404,
            detail="No traffic-aware route found.",
        )

    return {
        "route_found": True,
        "route": route,
        "route_edges": get_route_edges(route),
        "estimated_travel_time_seconds": round(
            travel_time_seconds,
            2,
        ),
        "estimated_travel_time_minutes": round(
            travel_time_seconds / 60,
            2,
        ),
        "traffic_data": traffic_data,
        "routing_algorithm": (
            "Custom Dijkstra with traffic-aware travel-time weights"
        ),
    }
