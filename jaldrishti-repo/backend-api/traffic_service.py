import os

import requests
from dotenv import load_dotenv

load_dotenv()

TOMTOM_API_KEY = os.getenv("TOMTOM_API_KEY")

TOMTOM_FLOW_URL = (
    "https://api.tomtom.com/traffic/services/4/flowSegmentData/"
    "absolute/10/json"
)


def get_live_traffic(latitude, longitude):
    """
    Gets current traffic details near a location.
    """
    if not TOMTOM_API_KEY:
        return None

    params = {
        "key": TOMTOM_API_KEY,
        "point": f"{latitude},{longitude}",
        "unit": "KMPH",
    }

    try:
        response = requests.get(
            TOMTOM_FLOW_URL,
            params=params,
            timeout=10,
        )

        response.raise_for_status()

        data = response.json()
        flow_data = data.get("flowSegmentData", {})

        return {
            "current_speed_kmph": flow_data.get("currentSpeed"),
            "free_flow_speed_kmph": flow_data.get(
                "freeFlowSpeed"
            ),
            "current_travel_time_seconds": flow_data.get(
                "currentTravelTime"
            ),
            "free_flow_travel_time_seconds": flow_data.get(
                "freeFlowTravelTime"
            ),
            "road_closure": flow_data.get("roadClosure", False),
        }

    except requests.RequestException:
        return None
