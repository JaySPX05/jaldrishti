"""
Mock risk data — stands in for Pair 1's precomputed lookup table.

Day 1, Hr 7-9: replace get_risk_segments() with a real read from wherever
Pair 1 writes their output (a JSON file, SQLite, whatever's fastest for
them to produce). Keep the return shape identical and nothing downstream
needs to change.

Coordinates below are placeholder points roughly in Bengaluru — swap for
Koramangala's actual centroid once the ward is confirmed (see check_swd_data.py
in data-pipeline/ for how that decision gets made).
"""

import hashlib

KNOWN_WARDS = ["koramangala", "bellandur", "yelahanka"]

# Rough placeholder centroid per ward — replace with real coordinates
# once Pair 1 hands off actual ward boundary data.
_WARD_CENTER = {
    "koramangala": (77.627, 12.935),
    "bellandur": (77.678, 12.926),
    "yelahanka": (77.596, 13.100),
}


def _fake_segment_geometry(center_lng: float, center_lat: float, i: int) -> list[list[float]]:
    """Generate a short, deterministic fake street segment near the ward center."""
    offset = (i % 10) * 0.002
    return [
        [center_lng + offset, center_lat + offset * 0.6],
        [center_lng + offset + 0.0015, center_lat + offset * 0.6 + 0.0012],
    ]


def _deterministic_risk(segment_id: str, timestamp: str) -> float:
    """
    Fake but STABLE risk score: same segment_id + timestamp always gives the
    same score. That matters for demo rehearsal — you want reproducible
    numbers, not random ones that change every refresh.
    """
    h = hashlib.md5(f"{segment_id}{timestamp}".encode()).hexdigest()
    return round((int(h[:4], 16) % 100) / 100, 2)


def get_risk_segments(ward_id: str, timestamp: str):
    """
    Returns a list of dicts matching the RiskSegment model, or None if the
    ward is unknown (the API layer turns that into a 404).
    """
    ward_id = ward_id.lower()
    if ward_id not in _WARD_CENTER:
        return None

    center_lng, center_lat = _WARD_CENTER[ward_id]
    segments = []
    for i in range(1, 16):  # 15 fake segments is plenty to make the map look real
        segment_id = f"seg_{i:04d}"
        risk = _deterministic_risk(segment_id, timestamp)
        segments.append(
            {
                "segment_id": segment_id,
                "geometry": _fake_segment_geometry(center_lng, center_lat, i),
                "risk_score": risk,
                "predicted_depth_cm": round(risk * 30, 1),  # arbitrary but plausible
                "confidence": 0.5,
            }
        )
    return segments
