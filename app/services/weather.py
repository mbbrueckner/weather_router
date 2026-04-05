"""Weather data retrieval from Open-Meteo API.

This module provides functionality to fetch weather forecasts for a list of
route points using the Open-Meteo API, returning a list of WeatherSnapshots.
"""

__author__ = "mbbrueckner"
__version__ = "1.1.0"

from datetime import datetime
from app.models import RoutePoint, WeatherSnapshot

import openmeteo_requests
import openmeteo_sdk.WeatherApiResponse as WeatherApiResponse

API_URL = "https://api.open-meteo.com/v1/forecast"

DEFAULT_MINUTELY_15 = [
    "wind_speed_10m",
    "wind_direction_10m",
    "wind_gusts_10m",
    "precipitation",
]


def get_weather(
    coords: list[RoutePoint],
    arrival_times: list[datetime],
) -> list[WeatherSnapshot]:
    """Fetch weather snapshots for a list of route points at their arrival times.

    Args:
        coords: List of RoutePoints to fetch weather for.
        arrival_times: List of expected arrival times, one per coordinate.

    Returns:
        List of WeatherSnapshots, one per coordinate.
    """
    params = _build_params(coords, arrival_times)
    client = openmeteo_requests.Client()
    responses = client.weather_api(API_URL, params=params)
    return _parse_responses(responses, coords, arrival_times)


def _build_params(
    coords: list[RoutePoint],
    arrival_times: list[datetime],
) -> dict:
    """Build the API request parameters.

    Args:
        coords: List of RoutePoints.
        arrival_times: List of arrival datetimes – used to determine date range.

    Returns:
        Dictionary of API parameters.
    """
    return {
        "latitude": [c.lat for c in coords],
        "longitude": [c.lon for c in coords],
        "minutely_15": ",".join(DEFAULT_MINUTELY_15),
        "wind_speed_unit": "ms",
        "start_date": arrival_times[0].date().isoformat(),
        "end_date": arrival_times[-1].date().isoformat(),
        "models": "best_match",
    }


def _parse_responses(
    responses: list[WeatherApiResponse],
    coords: list[RoutePoint],
    arrival_times: list[datetime],
) -> list[WeatherSnapshot]:
    """Parse API responses into WeatherSnapshot objects.

    Args:
        responses: List of API response objects, one per coordinate.
        coords: List of RoutePoints matching the responses.
        arrival_times: List of arrival times, one per coordinate.

    Returns:
        List of WeatherSnapshots for all coordinates.
    """
    snapshots = []

    for i, response in enumerate(responses):
        minutely = response.Minutely15()
        idx = _find_slot(minutely, arrival_times[i])

        snapshot = WeatherSnapshot(
            coords=coords[i],
            timestamp=arrival_times[i],
            wind_speed_ms=minutely.Variables(0).ValuesAsNumpy()[idx],
            wind_direction_deg=minutely.Variables(1).ValuesAsNumpy()[idx],
            wind_gusts_ms=minutely.Variables(2).ValuesAsNumpy()[idx],
            precipitation_mm_15=minutely.Variables(3).ValuesAsNumpy()[idx],
        )
        snapshots.append(snapshot)

    return snapshots


def _find_slot(minutely, target_time: datetime) -> int:
    """Find the index of the nearest 15-minute weather slot for a given time.

    Args:
        minutely: Open-Meteo Minutely15 response object.
        target_time: Target datetime to find the slot for.

    Returns:
        Index of the nearest slot, clamped to valid range.
    """
    start_unix = minutely.Time()
    interval = minutely.Interval()
    end_unix = minutely.TimeEnd()

    num_slots = int((end_unix - start_unix) / interval)
    target_unix = target_time.timestamp()

    idx = round((target_unix - start_unix) / interval)
    return max(0, min(idx, num_slots - 1))