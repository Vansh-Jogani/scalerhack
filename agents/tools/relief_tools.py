"""Relief tools — find nearest response centres and issue a structured relief plan."""

import math


FIND_NEAREST_CENTRE_TOOL = {
    "name": "find_nearest_centre",
    "description": (
        "Find the nearest response centres of a given type to the incident location. "
        "Call once per required centre type (e.g. FIRE_STATION, HOSPITAL, NDRF)."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "centre_type": {
                "type": "string",
                "enum": [
                    "FIRE_STATION", "HOSPITAL", "NDRF", "SDRF",
                    "CIVIL_DEFENCE", "AIRPORT_EMERGENCY",
                    "MUNICIPAL_EMERGENCY", "POLICE",
                ],
                "description": "Category of response centre needed",
            },
            "incident_lat":  {"type": "number", "description": "Incident latitude"},
            "incident_lon":  {"type": "number", "description": "Incident longitude"},
            "limit":         {"type": "integer", "description": "Max results (default 3)"},
        },
        "required": ["centre_type", "incident_lat", "incident_lon"],
    },
}

ISSUE_RELIEF_PLAN_TOOL = {
    "name": "issue_relief_plan",
    "description": "Issue a structured relief dispatch plan to coordinate immediate rescue response.",
    "input_schema": {
        "type": "object",
        "properties": {
            "incident_id": {"type": "string"},
            "dispatched_units": {
                "type": "array",
                "description": "Response units being dispatched immediately",
                "items": {
                    "type": "object",
                    "properties": {
                        "centre_id":   {"type": "string"},
                        "name":        {"type": "string"},
                        "type":        {"type": "string"},
                        "lat":         {"type": "number"},
                        "lon":         {"type": "number"},
                        "distance_m":  {"type": "number"},
                        "eta_min":     {"type": "number"},
                        "role":        {"type": "string", "description": "e.g. 'primary suppression', 'casualty reception'"},
                    },
                    "required": ["centre_id", "name", "type", "lat", "lon", "distance_m", "eta_min", "role"],
                },
            },
            "triage_sites": {
                "type": "array",
                "description": "Proposed on-site triage / casualty collection points",
                "items": {
                    "type": "object",
                    "properties": {
                        "lat":      {"type": "number"},
                        "lon":      {"type": "number"},
                        "capacity": {"type": "integer"},
                        "label":    {"type": "string"},
                    },
                    "required": ["lat", "lon", "capacity", "label"],
                },
            },
            "evacuation_routes": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "description": {"type": "string"},
                        "direction":   {"type": "string"},
                        "notes":       {"type": "string"},
                    },
                    "required": ["description", "direction", "notes"],
                },
            },
            "resource_gaps":     {"type": "array", "items": {"type": "string"}},
            "coordination_note": {"type": "string", "description": "Single-sentence overall coordination instruction"},
        },
        "required": [
            "incident_id", "dispatched_units", "triage_sites",
            "evacuation_routes", "resource_gaps", "coordination_note",
        ],
    },
}


def _haversine(lat1, lon1, lat2, lon2):
    R = 6_371_000.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (math.sin(dlat / 2) ** 2
         + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2) ** 2)
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def create_find_nearest_centre_handler(response_centres: list):
    async def find_nearest_centre(
        centre_type: str,
        incident_lat: float,
        incident_lon: float,
        limit: int = 3,
    ) -> dict:
        filtered = [c for c in response_centres if c.get("type") == centre_type]
        if not filtered:
            return {"status": "not_found", "centres": [], "message": f"No {centre_type} centres in dataset"}

        with_dist = sorted(
            filtered,
            key=lambda c: _haversine(incident_lat, incident_lon, c["lat"], c["lon"]),
        )[:limit]

        results = []
        for c in with_dist:
            dist_m = _haversine(incident_lat, incident_lon, c["lat"], c["lon"])
            eta_min = max(1, round(dist_m / (40_000 / 60)))  # ~40 km/h city traffic
            results.append({
                "centre_id":  c["id"],
                "name":       c["name"],
                "type":       c["type"],
                "lat":        c["lat"],
                "lon":        c["lon"],
                "distance_m": round(dist_m),
                "eta_min":    eta_min,
            })
        return {"status": "ok", "centres": results}

    return find_nearest_centre


def create_issue_relief_plan_handler(orchestrator):
    async def issue_relief_plan(**kwargs) -> dict:
        orchestrator.receive_agent4_plan(kwargs)
        return {"status": "ok", "message": "Relief plan issued to orchestrator"}
    return issue_relief_plan
