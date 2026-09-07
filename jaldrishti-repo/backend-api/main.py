"""
JalDrishti Backend — Risk API + Routing API

DECISION (this build): real data from Pair 1 will not arrive in time.
Shipping on synthetic data from data-pipeline/generate_synthetic_lookup.py,
served via data_loader.py. This is the actual dataset for the demo, not a
placeholder — treat it accordingly.

If real data arrives later: drop the real file at
data/processed/risk_lookup_<ward_id>.json, matching
contracts/risk-lookup-table-format.md. Nothing in this file changes.

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

import data_loader
import routing

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
    Returns risk scores for every street segment in a ward at a given timestep,
    read from the synthetic dataset via data_loader.py. If real data lands
    later, it's served from the exact same path with no code change here.
    """
    ts = timestamp or datetime.now(timezone.utc).isoformat()

    segments = data_loader.get_risk_segments(ward_id, ts)
    if segments is None:
        raise HTTPException(
            status_code=404,
            detail=f"No data for ward_id='{ward_id}'. "
                   f"Known wards: {data_loader.known_wards()}. "
                   f"Generate one: python data-pipeline/generate_synthetic_lookup.py {ward_id}",
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
    Risk-weighted routing. The graph-building and Dijkstra logic live in
    routing.py so the routing person can work on that file independently
    from the risk-endpoint / data-integration side of this file.

    Day 1: uses routing.build_synthetic_graph() + mock risk scores.
    Day 2: swap for Pair 1's real OSM extract of the pilot ward.
    """
    center = data_loader.WARD_CENTERS.get(ward_id.lower())
    if center is None:
        raise HTTPException(status_code=404, detail=f"Unknown ward_id: {ward_id}")

    graph = routing.build_synthetic_graph(*center)
    # Fake per-edge risk so the weighting logic is demonstrably working
    # before Pair 1's real segment-to-edge mapping exists.
    fake_risk = {f"edge_{i}": (i % 4) / 4 for i in range(graph.number_of_edges())}
    routing.apply_risk_scores(graph, fake_risk)

    result = routing.compute_route(graph, from_lng, from_lat, to_lng, to_lat)
    return RouteResponse(**result)
