"""Natural language → disaster type classifier."""

KEYWORDS: dict[str, list[str]] = {
    "fire": ["fire", "flame", "blaze", "burning", "wildfire", "smoke", "arson"],
    "structural_collapse": ["collapse", "building", "rubble", "structure", "earthquake", "demolition", "fallen"],
    "flood": ["flood", "water", "inundation", "surge", "overflow", "submerged", "rising water"],
    "industrial_hazard": ["chemical", "hazmat", "industrial", "gas", "toxic", "leak", "spill", "plant"],
    "maritime_sar": ["maritime", "ocean", "sea", "vessel", "boat", "overboard", "capsized", "offshore"],
}

SEVERITY_KEYWORDS: dict[str, str] = {
    "critical": "critical",
    "major": "high",
    "severe": "high",
    "minor": "low",
    "small": "low",
}


def classify_incident(text: str) -> str:
    """Map natural language description to a disaster_type string."""
    lower = text.lower()
    for disaster_type, kws in KEYWORDS.items():
        if any(kw in lower for kw in kws):
            return disaster_type
    return "fire"


def classify_severity(text: str) -> str:
    """Infer severity from natural language. Returns low/medium/high/critical."""
    lower = text.lower()
    for kw, severity in SEVERITY_KEYWORDS.items():
        if kw in lower:
            return severity
    return "medium"
