"""
JalDrishti Backend — Risk API + Routing API

Day 1 (Hr 1-4): this file returns MOCK data matching contracts/risk-api-schema.json.
That's the point — it unblocks Frontend immediately, before Pair 1 has real numbers.

Day 1 (Hr 7-9): swap `mock_data.get_risk_segments()` for a read from Pair 1's
precomputed lookup table. Nothing else in this file should need to change if
the contract shape stays frozen.

Day 2 (Hr 0-3): fill in the /api/v1/route endpoint with real Dijkstra routing
(see the TODO near the bottom).

Run locally:
    pip install -r requirements.txt
    uvicorn main:app --reload
    # then open http://127.0.0.1:8000/docs for interactive API docs
"""

from datetime import datetime, timezone
from typing import Optional

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

import mock_data

app = FastAPI(title="JalDrishti Risk API", version="1.0.0")

# Allow the frontend dev server to call this API from a different port/origin.
# Tighten this before any real deployment.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Response models — these mirror contracts/risk-api-schema.json exactly.
# If you change a field here, you MUST update the contract file too and
# tell the team, per the contract rule in the git workflow doc.
# ---------------------------------------------------------------------------

class RiskSegment(BaseModel):
    segment_id: str
    geometry: list[list[float]]  # [[lng, lat], [lng, lat], ...]
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


@app.get("/")
def health_check():
    return {"status": "ok", "service": "jaldrishti-backend"}


@app.get("/api/v1/risk", response_model=RiskResponse)
def get_risk(
    ward_id: str = Query(..., description="e.g. 'koramangala'"),
    timestamp: Optional[str] = Query(
        None, description="ISO8601. Defaults to now if omitted."
    ),
):
    """
    Returns risk scores for every street segment in a ward at a given timestep.

    Day 1: served from mock_data.py.
    Day 1 Hr 7-9: served from Pair 1's precomputed lookup table instead —
    swap the body of this function, keep the response shape identical.
    """
    ts = timestamp or datetime.now(timezone.utc).isoformat()

    segments = mock_data.get_risk_segments(ward_id, ts)
    if segments is None:
        raise HTTPException(
            status_code=404,
            detail=f"No data for ward_id='{ward_id}'. "
                   f"Known wards: {mock_data.KNOWN_WARDS}",
        )

    return RiskResponse(
        ward_id=ward_id,
        timestamp=ts,
        forecast_window_minutes=180,
        segments=segments,
    )


@app.get("/api/v1/route", response_model=RouteResponse)
def get_route(
    from_lng: float = Query(..., alias="from_lng"),
    from_lat: float = Query(..., alias="from_lat"),
    to_lng: float = Query(..., alias="to_lng"),
    to_lat: float = Query(..., alias="to_lat"),
    ward_id: str = Query(...),
):
    """
    Day 1: stub response so Frontend can wire up the "show route" button.

    Day 2 (Hr 0-3): replace this with real Dijkstra over the OSM road graph,
    weighted by risk scores from get_risk(). Rough shape of that work:

        1. Load the ward's road graph (networkx.Graph) from Pair 1's OSM extract
        2. Snap (from_lng, from_lat) and (to_lng, to_lat) to nearest graph nodes
        3. Set each edge's weight = base_distance * (1 + risk_penalty_factor * risk_score)
        4. nx.shortest_path(graph, source, target, weight="weight")
        5. Convert the resulting node path back to [[lng, lat], ...] coordinates
        6. Return which segments (if any) scored above your risk threshold
           and were therefore routed around
    """
    # TODO (Day 2, Pair 2): replace this stub with real Dijkstra routing.
    return RouteResponse(
        path=[[from_lng, from_lat], [to_lng, to_lat]],
        avoided_segments=[],
        risk_penalty_applied=False,
    )
