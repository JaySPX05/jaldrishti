"""
Routing engine — owned by Pair 2's routing person.

This file is deliberately separate from main.py and risk_data.py so you can
work on it without touching the same file as your pair partner (who owns
the risk API / data integration side). That keeps git merges clean.

Day 1: build and test this against the synthetic risk data (see
data_loader.py and data-pipeline/generate_synthetic_lookup.py) — you don't
need real OSM data to start on the routing algorithm itself.

Day 2, Hr 0-3: swap the synthetic road graph below for Pair 1's real OSM
extract of the pilot ward. The algorithm and function signature shouldn't
need to change — only where the graph comes from.
"""

import math
from typing import Optional

import networkx as nx


def build_synthetic_graph(center_lng: float, center_lat: float) -> nx.Graph:
    """
    A small fake road grid so you can build and test Dijkstra TODAY, without
    waiting on Pair 1's real OSM extract. 5x5 grid of nodes, connected to
    their neighbors — enough to prove the algorithm works end-to-end.

    Day 2: replace this with something like:
        import osmnx as ox
        graph = ox.graph_from_place("Koramangala, Bengaluru, India", network_type="drive")
    """
    G = nx.Graph()
    step = 0.003
    size = 5

    for i in range(size):
        for j in range(size):
            node_id = f"n_{i}_{j}"
            lng = center_lng + i * step
            lat = center_lat + j * step
            G.add_node(node_id, lng=lng, lat=lat)

    for i in range(size):
        for j in range(size):
            here = f"n_{i}_{j}"
            if i + 1 < size:
                _add_edge(G, here, f"n_{i+1}_{j}")
            if j + 1 < size:
                _add_edge(G, here, f"n_{i}_{j+1}")

    return G


def _add_edge(G: nx.Graph, a: str, b: str):
    la = G.nodes[a]
    lb = G.nodes[b]
    dist_m = _haversine_m(la["lng"], la["lat"], lb["lng"], lb["lat"])
    G.add_edge(a, b, base_distance_m=dist_m, risk_score=0.0)


def _haversine_m(lng1, lat1, lng2, lat2) -> float:
    """Straight-line distance in metres between two lng/lat points."""
    R = 6371000
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lng2 - lng1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return 2 * R * math.asin(math.sqrt(a))


def _nearest_node(G: nx.Graph, lng: float, lat: float) -> str:
    """Snap an arbitrary lng/lat to the closest graph node."""
    best_node, best_dist = None, float("inf")
    for node, data in G.nodes(data=True):
        d = _haversine_m(lng, lat, data["lng"], data["lat"])
        if d < best_dist:
            best_node, best_dist = node, d
    return best_node


def apply_risk_scores(G: nx.Graph, risk_lookup: dict[str, float]):
    """
    Stamp risk scores onto graph edges before routing.

    risk_lookup maps some identifier -> risk_score (0-1). Exactly how you key
    this depends on how Pair 1's real data lines up edges to segment_ids —
    for the mock/synthetic graph, this just assigns a score by edge index so
    you can prove the weighting logic works before real data exists.
    """
    for i, (u, v) in enumerate(G.edges()):
        key = f"edge_{i}"
        G[u][v]["risk_score"] = risk_lookup.get(key, 0.0)


def compute_route(
    G: nx.Graph,
    from_lng: float,
    from_lat: float,
    to_lng: float,
    to_lat: float,
    risk_penalty_factor: float = 5.0,
    risk_threshold: float = 0.7,
) -> dict:
    """
    Risk-weighted Dijkstra. Higher risk_score on an edge makes it more
    "expensive" to traverse, so the shortest-weighted-path naturally
    avoids high-risk segments without hard-blocking them.

    risk_penalty_factor: how strongly risk affects the route. 0 = ignore
    risk entirely (pure shortest path). Higher = more willing to take a
    longer physical route to avoid risk.
    """
    source = _nearest_node(G, from_lng, from_lat)
    target = _nearest_node(G, to_lng, to_lat)

    for u, v, data in G.edges(data=True):
        data["weight"] = data["base_distance_m"] * (1 + risk_penalty_factor * data["risk_score"])

    try:
        node_path = nx.shortest_path(G, source, target, weight="weight")
    except nx.NetworkXNoPath:
        return {"path": [], "avoided_segments": [], "risk_penalty_applied": False}

    coords = [[G.nodes[n]["lng"], G.nodes[n]["lat"]] for n in node_path]

    avoided = []
    for u, v, data in G.edges(data=True):
        if data["risk_score"] >= risk_threshold:
            if not (u in node_path and v in node_path and
                     abs(node_path.index(u) - node_path.index(v)) == 1):
                avoided.append(f"{u}-{v}")

    return {
        "path": coords,
        "avoided_segments": avoided,
        "risk_penalty_applied": risk_penalty_factor > 0,
    }
