"""Classifier — maps incident_type to swarm config.

Pure lookup from SWARM_CAPABILITIES decision table.
NO NLP, NO keyword matching, NO LLM.
Per SPEC.md: swarm selection is locked to a decision table in code.
"""

# Verbatim from SPEC.md
SWARM_CAPABILITIES = {
    "fire": {
        "swarm": "thermal_rotary",
        "drones": 3,
        "sensors": ["thermal_camera", "gas_detector", "wind_sensor"],
        "altitude": 50,
        "speed": 8,
        "priority_tasks": [
            "map_fire_perimeter",
            "identify_hotspots",
            "detect_trapped_persons",
            "assess_spread_direction",
        ],
        "constraint": "maintain_upwind_position",
    },
    "structural_collapse": {
        "swarm": "micro_search_rotary",
        "drones": 4,
        "sensors": ["acoustic_detector", "co2_sensor", "thermal", "visual_hd"],
        "altitude": 15,
        "speed": 4,
        "priority_tasks": [
            "map_void_spaces",
            "detect_survivors",
            "assess_structural_integrity",
            "identify_egress_paths",
        ],
        "constraint": "avoid_zones_integrity_below_0.2",
    },
    "flood": {
        "swarm": "fixed_wing_extended",
        "drones": 2,
        "sensors": ["visual_hd", "thermal", "depth_estimation"],
        "altitude": 80,
        "speed": 18,
        "priority_tasks": [
            "map_flood_extent",
            "identify_isolated_survivors",
            "assess_flow_direction",
            "find_safe_approach_routes",
        ],
        "constraint": "maintain_visual_line_of_sight",
    },
    "industrial_hazard": {
        "swarm": "standoff_rotary",
        "drones": 2,
        "sensors": ["gas_spectrometer", "thermal", "visual_hd"],
        "altitude": 100,
        "speed": 6,
        "priority_tasks": [
            "identify_hazard_source",
            "map_exclusion_zone",
            "detect_spread_direction",
            "assess_secondary_risk",
        ],
        "constraint": "minimum_200m_standoff_from_source",
    },
    "maritime_sar": {
        "swarm": "fixed_wing_endurance",
        "drones": 3,
        "sensors": ["visual_hd", "thermal", "ais_receiver"],
        "altitude": 150,
        "speed": 22,
        "priority_tasks": [
            "expanding_square_search",
            "detect_persons_in_water",
            "track_drift_objects",
            "coordinate_vessel_response",
        ],
        "constraint": "maintain_comms_relay_chain",
    },
}

VALID_TYPES = list(SWARM_CAPABILITIES.keys())


def classify(incident_type: str) -> dict:
    """Map incident_type string to swarm configuration dict.

    This is a pure lookup — no NLP, no inference, no LLM.
    Raises ValueError for unknown types.
    """
    if incident_type not in SWARM_CAPABILITIES:
        raise ValueError(
            f"Unknown incident type: '{incident_type}'. "
            f"Valid types: {VALID_TYPES}"
        )
    return SWARM_CAPABILITIES[incident_type]
