"""Web search tools — live data retrieval for agent reasoning."""

import httpx
import structlog

logger = structlog.get_logger()

WEB_SEARCH_WEATHER_TOOL = {
    "name": "get_live_weather",
    "description": (
        "Fetch live weather conditions at given coordinates using Open-Meteo API. "
        "Returns temperature, wind speed/direction, humidity, and weather description. "
        "Use this before starting a survey to understand environmental conditions "
        "that affect fire spread, visibility, and drone operations."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "lat": {"type": "number", "description": "Latitude of the location"},
            "lon": {"type": "number", "description": "Longitude of the location"},
        },
        "required": ["lat", "lon"],
    },
}

WMO_WEATHER_CODES = {
    0: "Clear sky",
    1: "Mainly clear",
    2: "Partly cloudy",
    3: "Overcast",
    45: "Fog",
    48: "Depositing rime fog",
    51: "Light drizzle",
    53: "Moderate drizzle",
    55: "Dense drizzle",
    61: "Slight rain",
    63: "Moderate rain",
    65: "Heavy rain",
    71: "Slight snow",
    73: "Moderate snow",
    75: "Heavy snow",
    77: "Snow grains",
    80: "Slight rain showers",
    81: "Moderate rain showers",
    82: "Violent rain showers",
    85: "Slight snow showers",
    86: "Heavy snow showers",
    95: "Thunderstorm",
    96: "Thunderstorm with slight hail",
    99: "Thunderstorm with heavy hail",
}


def create_get_live_weather_handler():
    async def handler(lat: float, lon: float, **kwargs) -> dict:
        url = (
            f"https://api.open-meteo.com/v1/forecast"
            f"?latitude={lat}&longitude={lon}"
            f"&current=temperature_2m,wind_speed_10m,wind_direction_10m,"
            f"relative_humidity_2m,weather_code"
        )
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(url)
                resp.raise_for_status()
                data = resp.json()

            current = data.get("current", {})
            weather_code = current.get("weather_code", 0)
            result = {
                "status": "ok",
                "data": {
                    "temperature_c": current.get("temperature_2m"),
                    "wind_speed_ms": current.get("wind_speed_10m"),
                    "wind_direction_deg": current.get("wind_direction_10m"),
                    "humidity_pct": current.get("relative_humidity_2m"),
                    "weather_code": weather_code,
                    "description": WMO_WEATHER_CODES.get(weather_code, "Unknown"),
                },
                "source": "open-meteo.com",
                "coordinates": {"lat": lat, "lon": lon},
            }
            logger.info("weather_fetched", lat=lat, lon=lon, wind=result["data"]["wind_speed_ms"])
            return result

        except httpx.HTTPError as e:
            logger.warning("weather_fetch_failed", error=str(e), lat=lat, lon=lon)
            return {
                "status": "error",
                "message": f"Weather API unavailable: {e}",
                "data": {
                    "temperature_c": None,
                    "wind_speed_ms": None,
                    "wind_direction_deg": None,
                    "humidity_pct": None,
                    "weather_code": None,
                    "description": "Weather data unavailable",
                },
            }

    return handler
