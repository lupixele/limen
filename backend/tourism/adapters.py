"""External API Adapters with strict timeouts, provenance, and truthful failure reporting."""
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
import httpx
from zoneinfo import ZoneInfo

from tourism.provenance import DataSourceType, Provenance

logger = logging.getLogger("tourism.adapters")
TIMEOUT = 4.0  # bounded 4s HTTP timeout per specification


class WeatherAdapter:
    """Open-Meteo Weather adapter with truthful fallback / error handling."""

    @staticmethod
    async def get_current_and_forecast(
        latitude: float,
        longitude: float,
        timezone_str: str = "Asia/Kolkata"
    ) -> Dict[str, Any]:
        url = (
            f"https://api.open-meteo.com/v1/forecast"
            f"?latitude={latitude}&longitude={longitude}"
            f"&current=temperature_2m,relative_humidity_2m,apparent_temperature,precipitation,weather_code,wind_speed_10m"
            f"&hourly=temperature_2m,precipitation_probability,weather_code"
            f"&daily=temperature_2m_max,temperature_2m_min,precipitation_probability_max,weather_code"
            f"&timezone={timezone_str}"
        )
        try:
            async with httpx.AsyncClient(timeout=TIMEOUT) as client:
                resp = await client.get(url)
                if resp.status_code == 200:
                    data = resp.json()
                    prov = Provenance(
                        source_name="Open-Meteo Weather API",
                        source_type=DataSourceType.LIVE,
                        source_url="https://open-meteo.com/en/docs",
                        confidence=0.98,
                        notes="Live real-time weather and official forecast."
                    )
                    return {
                        "status": "success",
                        "provenance": prov.to_dict(),
                        "current": data.get("current", {}),
                        "daily": data.get("daily", {}),
                        "hourly": data.get("hourly", {})
                    }
                else:
                    return {
                        "status": "error",
                        "error": f"Open-Meteo returned HTTP {resp.status_code}",
                        "provenance": Provenance(
                            source_name="Open-Meteo Weather API",
                            source_type=DataSourceType.UNKNOWN,
                            confidence=0.0,
                            notes=f"API returned status {resp.status_code}"
                        ).to_dict()
                    }
        except Exception as e:
            logger.warning(f"WeatherAdapter error: {e}")
            return {
                "status": "error",
                "error": f"Weather lookup failed: {str(e)}",
                "provenance": Provenance(
                    source_name="Open-Meteo Weather API",
                    source_type=DataSourceType.UNKNOWN,
                    confidence=0.0,
                    notes=f"Connection failure: {str(e)}"
                ).to_dict()
            }


class RoutingAdapter:
    """OSRM public routing adapter for real driving transit calculation and explicit fallbacks."""

    @staticmethod
    def calculate_haversine_estimate(
        origin_lat: float,
        origin_lon: float,
        dest_lat: float,
        dest_lon: float,
        mode: str = "driving"
    ) -> Dict[str, Any]:
        """Deterministic geometric travel estimate with explicit FALLBACK / SIMULATED provenance."""
        import math
        R = 6371.0  # Earth radius in km
        dlat = math.radians(dest_lat - origin_lat)
        dlon = math.radians(dest_lon - origin_lon)
        a = (
            math.sin(dlat / 2) ** 2
            + math.cos(math.radians(origin_lat))
            * math.cos(math.radians(dest_lat))
            * math.sin(dlon / 2) ** 2
        )
        c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
        dist_km = round(R * c * 1.25, 2)  # 1.25x road curvature factor

        if mode == "walking":
            speed = 4.5  # standard pedestrian speed in km/h
            duration_min = max(2.0, round((dist_km / speed) * 60, 1))
            prov = Provenance(
                source_name="Pedestrian Walking Model (Geometric)",
                source_type=DataSourceType.SIMULATED,
                confidence=0.85,
                notes="Pedestrian walking duration estimated at 4.5 km/h (OSRM public server does not support pedestrian routing)."
            )
        else:
            speed = 25.0  # average city driving speed in km/h
            duration_min = max(5.0, round((dist_km / speed) * 60, 1))
            prov = Provenance(
                source_name="Geometric Haversine Fallback",
                source_type=DataSourceType.FALLBACK,
                confidence=0.70,
                notes="Live routing service unavailable; estimated via Haversine road factor 1.25x and 25 km/h."
            )

        return {
            "status": "success",
            "duration_min": duration_min,
            "distance_km": dist_km,
            "mode": mode,
            "provenance": prov.to_dict()
        }

    @staticmethod
    async def get_route(
        origin_lat: float,
        origin_lon: float,
        dest_lat: float,
        dest_lon: float,
        mode: str = "driving"
    ) -> Dict[str, Any]:
        """Queries OSRM for driving routes. Explicitly rejects false live claims for unsupported modes."""
        if mode != "driving":
            # OSRM public demo server ONLY supports the car profile.
            # Querying walking/foot on router.project-osrm.org incorrectly returns car routes.
            # Use deterministic pedestrian model with clear SIMULATED provenance.
            return RoutingAdapter.calculate_haversine_estimate(origin_lat, origin_lon, dest_lat, dest_lon, mode=mode)

        url = (
            f"https://router.project-osrm.org/route/v1/driving/"
            f"{origin_lon},{origin_lat};{dest_lon},{dest_lat}?overview=false"
        )
        try:
            async with httpx.AsyncClient(timeout=TIMEOUT) as client:
                resp = await client.get(url)
                if resp.status_code == 200:
                    data = resp.json()
                    routes = data.get("routes", [])
                    if routes:
                        r0 = routes[0]
                        duration_sec = r0.get("duration", 0)
                        distance_meters = r0.get("distance", 0)
                        prov = Provenance(
                            source_name="OSRM Public Routing API",
                            source_type=DataSourceType.LIVE,
                            source_url="https://project-osrm.org/",
                            confidence=0.95,
                            notes="Real road network routing for driving mode."
                        )
                        return {
                            "status": "success",
                            "duration_min": round(duration_sec / 60, 1),
                            "distance_km": round(distance_meters / 1000, 2),
                            "mode": "driving",
                            "provenance": prov.to_dict()
                        }
            # If OSRM returned non-200 or empty routes, report failure truthfully
            logger.warning(f"OSRM returned status {resp.status_code}")
            return {
                "status": "error",
                "error": f"OSRM returned status {resp.status_code}",
                "mode": mode,
                "provenance": Provenance(
                    source_name="OSRM Public Routing API",
                    source_type=DataSourceType.UNKNOWN,
                    confidence=0.0,
                    notes=f"OSRM returned status {resp.status_code}"
                ).to_dict()
            }
        except Exception as e:
            logger.warning(f"RoutingAdapter live call failed: {e}")
            return {
                "status": "error",
                "error": f"OSRM connection failed: {str(e)}",
                "mode": mode,
                "provenance": Provenance(
                    source_name="OSRM Public Routing API",
                    source_type=DataSourceType.UNKNOWN,
                    confidence=0.0,
                    notes=f"Live routing unreachable: {str(e)}"
                ).to_dict()
            }
