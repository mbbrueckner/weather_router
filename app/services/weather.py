"""Weather data retrieval from Open-Meteo API.

This module provides functionality to fetch weather forecasts for a list of
route points using the Open-Meteo API, returning the data as a pandas DataFrame.
"""

__author__ = "mbbrueckner"
__version__ = "0.1.0"

import openmeteo_requests
import pandas as pd
from datetime import date
from app.gpx_parser import RoutePoint

API_URL = "https://api.open-meteo.com/v1/forecast"

DEFAULT_MINUTELY_15 = [
    "wind_speed_10m",
    "wind_direction_10m",
    "wind_gusts_10m",
    "precipitation",
]


def get_weather(
    coords: list[RoutePoint],
    start_date: date,
    end_date: date | None = None,
    minutely_15: list[str] = DEFAULT_MINUTELY_15,
) -> pd.DataFrame:
    """Fetch minutely weather forecasts for a list of route points.

    Args:
        coords: List of RoutePoints to fetch weather for.
        start_date: Start date of the forecast.
        end_date: End date of the forecast. Defaults to start_date.
        minutely_15: List of weather variables to fetch.

    Returns:
        DataFrame with columns: latitude, longitude, date, and one column
        per requested weather variable.
    """
    if end_date is None:
        end_date = start_date

    params = _build_params(coords, start_date, end_date, minutely_15)
    client = openmeteo_requests.Client()
    responses = client.weather_api(API_URL, params=params)
    return _parse_responses(responses, minutely_15)


def _build_params(
    coords: list[RoutePoint],
    start_date: date,
    end_date: date,
    minutely_15: list[str],
) -> dict:
    """Build the API request parameters.

    Args:
        coords: List of RoutePoints.
        start_date: Start date of the forecast.
        end_date: End date of the forecast.
        minutely_15: List of weather variables to fetch.

    Returns:
        Dictionary of API parameters.
    """
    return {
        "latitude": [c.lat for c in coords],
        "longitude": [c.lon for c in coords],
        "minutely_15": ",".join(minutely_15),
        "wind_speed_unit": "ms",
        "start_date": start_date.isoformat(),
        "end_date": end_date.isoformat(),
    }


def _parse_responses(responses: list, variable_names: list[str]) -> pd.DataFrame:
    """Parse API responses into a single DataFrame.

    Args:
        responses: List of API response objects, one per coordinate.
        variable_names: List of weather variable names matching response order.

    Returns:
        Combined DataFrame for all coordinates.
    """
    frames = []

    for response in responses:
        minutely = response.Minutely15()
        data = {
            "latitude": response.Latitude(),
            "longitude": response.Longitude(),
            "date": pd.date_range(
                start=pd.to_datetime(minutely.Time(), unit="s", utc=True),
                end=pd.to_datetime(minutely.TimeEnd(), unit="s", utc=True),
                freq=pd.Timedelta(seconds=minutely.Interval()),
                inclusive="left",
            ),
        }
        for i, name in enumerate(variable_names):
            data[name] = minutely.Variables(i).ValuesAsNumpy()

        frames.append(pd.DataFrame(data))

    return pd.concat(frames, ignore_index=True)