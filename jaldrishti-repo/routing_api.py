import osmnx as ox
import networkx as nx

# ---------- load the real road network ----------

def build_graph(place_name):
    """
    place_name should be specific, e.g. 'Koramangala, Bengaluru, India'
    or 'HSR Layout, Bengaluru, Karnataka, India'
    """
    G = ox.graph_from_place(place_name, network_type="drive")
    for u, v, k, data in G.edges(keys=True, data=True):
        # placeholder until Pair 2's /risk endpoint data is wired in
        data["risk_score"] = 0.0
    return G


# ---------- apply real risk scores from Pair 2's API ----------

def apply_risk_scores(G, risk_lookup):
    """
    risk_lookup: dict mapping edge identifiers (e.g. osmid) to a risk score 0-1.
    You'll need to match Pair 2's segment IDs to this graph's edge osmids.
    """
    for u, v, k, data in G.edges(keys=True, data=True):
        osmid = data.get("osmid")
        if isinstance(osmid, list):
            osmid = osmid[0]
        risk = risk_lookup.get(osmid, 0.0)
        data["risk_score"] = risk
    return G


def apply_risk_weights(G, block_threshold=0.8):
    for u, v, k, data in G.edges(keys=True, data=True):
        risk = data.get("risk_score", 0.0)
        if risk >= block_threshold:
            data["risk_cost"] = float("inf")
        else:
            data["risk_cost"] = data["length"] * (1 + risk * 10)
    return G


# ---------- routing ----------

def get_route(G, start_lat, start_lon, end_lat, end_lon, weight="risk_cost"):
    orig = ox.distance.nearest_nodes(G, start_lon, start_lat)
    dest = ox.distance.nearest_nodes(G, end_lon, end_lat)
    try:
        path = nx.shortest_path(G, orig, dest, weight=weight)
        coords = [(G.nodes[n]["y"], G.nodes[n]["x"]) for n in path]
        return coords
    except nx.NetworkXNoPath:
        return None


# ---------- quick test ----------

if __name__ == "__main__":
    PLACE_NAME = "Koramangala, Bengaluru, India"  # <-- replace with actual pilot ward

    G = build_graph(PLACE_NAME)
    G = apply_risk_weights(G)  # all risk_score=0 for now, real scores come later

    # pick two real coordinates inside your ward to test with
    start_lat, start_lon = 12.9352, 77.6146
    end_lat, end_lon = 12.9279, 77.6271

    route = get_route(G, start_lat, start_lon, end_lat, end_lon)
    print("Route:", route)
