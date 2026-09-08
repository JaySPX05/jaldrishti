"""
FastAPI wrapper around the routing logic — returns GeoJSON so Pair 3's
Leaflet dashboard can drop the response straight onto the map.

Run with: uvicorn routing_api:app --reload
Then visit http://localhost:8000/docs to test it interactively.
"""

import os
import json
import osmnx as ox
import networkx as nx
from fastapi import FastAPI, HTTPException

app = FastAPI(title="JalDrishti Routing API")

PLACE_NAME = "Koramangala, Bengaluru, India"  # confirmed pilot ward
RISK_LOOKUP_PATH = os.path.join(os.path.dirname(__file__), "risk_lookup_koramangala.json")


# ============================================================
# GRAPH SETUP — built once at startup, cached in memory
# ============================================================

_state = {"graph": None, "risk_data": None}


def get_graph():
    """Builds (or returns cached) the real OSM road graph for the ward."""
    if _state["graph"] is None:
        print(f"Building graph for {PLACE_NAME} ...")
        G = ox.graph_from_place(PLACE_NAME, network_type="drive")
        for u, v, k, data in G.edges(keys=True, data=True):
            data["risk_score"] = 0.0  # default until risk data is applied
        _state["graph"] = G
    return _state["graph"]


# ============================================================
# RISK DATA — real data if available, mock placeholder otherwise
# ============================================================

def load_risk_data():
    """
    Loads Pair 1's precomputed risk lookup table if it exists.
    Expected format (matches risk_lookup_koramangala.json):
    {
      "timesteps": {
        "2026-09-07T15:00:00+00:00": [
          {"segment_id": "...", "geometry": [[lon,lat],[lon,lat]], "risk_score": 0.68, ...},
          ...
        ],
        ...
      }
    }
    """
    if _state["risk_data"] is not None:
        return _state["risk_data"]

    if os.path.exists(RISK_LOOKUP_PATH):
        with open(RISK_LOOKUP_PATH, "r") as f:
            _state["risk_data"] = json.load(f)
        print(f"Loaded real risk data from {RISK_LOOKUP_PATH}")
    else:
        # ---- MOCK PLACEHOLDER: remove once real data is always present ----
        print("No risk lookup file found — using mock (all-zero risk) placeholder.")
        _state["risk_data"] = {"timesteps": {}}

    return _state["risk_data"]


def segment_midpoint(geometry):
    """geometry: [[lon,lat],[lon,lat]] -> (lat, lon) midpoint."""
    lons = [pt[0] for pt in geometry]
    lats = [pt[1] for pt in geometry]
    return (sum(lats) / len(lats), sum(lons) / len(lons))


def apply_risk_to_graph(G, timestep=None):
    """
    Matches Pair 1's segments to graph edges by nearest midpoint, since the
    real data identifies segments by geometry, not OSM edge IDs.
    NOTE: this is an approximate spatial match — good enough for a 2-day demo,
    not survey-grade. If Pair 1's segment_ids ever align with osmids directly,
    swap this for a direct dict lookup instead (much faster).
    """
    risk_data = load_risk_data()
    timesteps = risk_data.get("timesteps", {})

    if not timesteps:
        # mock mode — leave graph at its default risk_score = 0.0
        return G

    ts_key = timestep if timestep in timesteps else next(iter(timesteps))
    segments = timesteps[ts_key]

    if not segments:
        return G

    seg_points = [segment_midpoint(s["geometry"]) for s in segments]
    seg_risks = [s["risk_score"] for s in segments]

    for u, v, k, data in G.edges(keys=True, data=True):
        edge_lat = (G.nodes[u]["y"] + G.nodes[v]["y"]) / 2
        edge_lon = (G.nodes[u]["x"] + G.nodes[v]["x"]) / 2

        # nearest segment by simple euclidean distance on lat/lon (fine at this scale)
        best_dist = float("inf")
        best_risk = 0.0
        for (slat, slon), srisk in zip(seg_points, seg_risks):
            d = (edge_lat - slat) ** 2 + (edge_lon - slon) ** 2
            if d < best_dist:
                best_dist = d
                best_risk = srisk

        data["risk_score"] = best_risk

    return G


def apply_risk_weights(G, block_threshold=0.8):
    for u, v, k, data in G.edges(keys=True, data=True):
        risk = data.get("risk_score", 0.0)
        if risk >= block_threshold:
            data["risk_cost"] = float("inf")
        else:
            data["risk_cost"] = data["length"] * (1 + risk * 10)
    return G


# ============================================================
# ROUTING
# ============================================================

def get_route_coords(G, start_lat, start_lon, end_lat, end_lon, weight="risk_cost"):
    orig = ox.distance.nearest_nodes(G, start_lon, start_lat)
    dest = ox.distance.nearest_nodes(G, end_lon, end_lat)
    try:
        path = nx.shortest_path(G, orig, dest, weight=weight)
        return [(G.nodes[n]["y"], G.nodes[n]["x"]) for n in path]
    except nx.NetworkXNoPath:
        return None


def coords_to_geojson_feature(coords, properties=None):
    """coords: list of (lat, lon) -> GeoJSON LineString feature (GeoJSON wants [lon, lat])."""
    if coords is None:
        return None
    return {
        "type": "Feature",
        "properties": properties or {},
        "geometry": {
            "type": "LineString",
            "coordinates": [[lon, lat] for lat, lon in coords],
        },
    }


# ============================================================
# ENDPOINTS
# ============================================================

@app.get("/")
def root():
    risk_data = load_risk_data()
    has_real_data = bool(risk_data.get("timesteps"))
    return {
        "status": "ok",
        "ward": PLACE_NAME,
        "using_real_risk_data": has_real_data,
    }


@app.get("/route")
def route(start_lat: float, start_lon: float, end_lat: float, end_lon: float, timestep: str = None):
    """
    Returns a GeoJSON FeatureCollection with two routes:
      - 'shortest' : plain shortest-distance route (ignores risk)
      - 'safe'     : risk-weighted route (avoids/penalizes flooded segments)

    Drop the returned FeatureCollection straight into Leaflet's L.geoJSON().

    If no real risk data is present yet, 'safe' will equal 'shortest' since
    every edge defaults to risk_score = 0.0 — that's the placeholder space
    for real data, not a bug.
    """
    G = get_graph()
    G = apply_risk_to_graph(G, timestep=timestep)
    G = apply_risk_weights(G)

    shortest_coords = get_route_coords(G, start_lat, start_lon, end_lat, end_lon, weight="length")
    safe_coords = get_route_coords(G, start_lat, start_lon, end_lat, end_lon, weight="risk_cost")

    if shortest_coords is None and safe_coords is None:
        raise HTTPException(status_code=404, detail="No route found between the given points.")

    features = []
    shortest_feature = coords_to_geojson_feature(shortest_coords, {"route_type": "shortest"})
    safe_feature = coords_to_geojson_feature(safe_coords, {"route_type": "safe"})
    if shortest_feature:
        features.append(shortest_feature)
    if safe_feature:
        features.append(safe_feature)

    risk_data = load_risk_data()
    return {
        "type": "FeatureCollection",
        "features": features,
        "meta": {
            "using_real_risk_data": bool(risk_data.get("timesteps")),
            "timestep_used": timestep,
        },
    }
