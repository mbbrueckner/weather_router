"""Tests for app/services/weather.py"""

import pytest
import numpy as np
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

from app.models import RoutePoint, WeatherSnapshot
from app.services.weather import (
    get_weather,
    _build_params,
    _parse_responses,
    _find_slot,
    DEFAULT_MINUTELY_15,
)


# --- Fixtures ---

def make_arrival_times(*hours: int) -> list[datetime]:
    """Create UTC datetimes at given hours on 2026-04-06."""
    return [
        datetime(2026, 4, 6, h, 0, 0, tzinfo=timezone.utc)
        for h in hours
    ]

def make_coords(*pairs: tuple[float, float]) -> list[RoutePoint]:
    return [RoutePoint(lat=lat, lon=lon) for lat, lon in pairs]

def make_mock_response(
    lat: float,
    lon: float,
    n_steps: int = 96,
    start_unix: int = 0,
    interval: int = 900,
) -> MagicMock:
    """Build a mock Open-Meteo API response."""
    response = MagicMock()
    response.Latitude.return_value = lat
    response.Longitude.return_value = lon

    minutely = MagicMock()
    minutely.Time.return_value = start_unix
    minutely.TimeEnd.return_value = start_unix + n_steps * interval
    minutely.Interval.return_value = interval

    def make_variable(idx: int) -> MagicMock:
        var = MagicMock()
        var.ValuesAsNumpy.return_value = np.full(n_steps, float(idx) * 10)
        return var

    minutely.Variables.side_effect = make_variable
    response.Minutely15.return_value = minutely
    return response


# --- _build_params ---

class TestBuildParams:
    def setup_method(self):
        self.coords = make_coords((48.0, 11.0), (48.5, 11.5))
        self.arrival_times = make_arrival_times(9, 10)

    def test_latitudes(self):
        params = _build_params(self.coords, self.arrival_times)
        assert params["latitude"] == [48.0, 48.5]

    def test_longitudes(self):
        params = _build_params(self.coords, self.arrival_times)
        assert params["longitude"] == [11.0, 11.5]

    def test_start_date_from_first_arrival(self):
        params = _build_params(self.coords, self.arrival_times)
        assert params["start_date"] == "2026-04-06"

    def test_end_date_from_last_arrival(self):
        params = _build_params(self.coords, self.arrival_times)
        assert params["end_date"] == "2026-04-06"

    def test_multiday_tour_date_range(self):
        """Tour starting late and ending next day."""
        times = [
            datetime(2026, 4, 6, 23, 0, tzinfo=timezone.utc),
            datetime(2026, 4, 7, 1, 0, tzinfo=timezone.utc),
        ]
        params = _build_params(self.coords, times)
        assert params["start_date"] == "2026-04-06"
        assert params["end_date"] == "2026-04-07"

    def test_minutely_variables_joined(self):
        params = _build_params(self.coords, self.arrival_times)
        assert params["minutely_15"] == ",".join(DEFAULT_MINUTELY_15)

    def test_wind_speed_unit_km_h(self):
        params = _build_params(self.coords, self.arrival_times)
        assert params["wind_speed_unit"] == "ms"

    def test_models_best_match(self):
        params = _build_params(self.coords, self.arrival_times)
        assert params["models"] == "best_match"


# --- _find_slot ---

class TestFindSlot:
    def make_minutely(self, start_unix: int, n_steps: int = 96, interval: int = 900):
        minutely = MagicMock()
        minutely.Time.return_value = start_unix
        minutely.TimeEnd.return_value = start_unix + n_steps * interval
        minutely.Interval.return_value = interval
        return minutely

    def test_first_slot(self):
        minutely = self.make_minutely(start_unix=0)
        target = datetime(1970, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
        assert _find_slot(minutely, target) == 0

    def test_exact_slot_match(self):
        start = int(datetime(2026, 4, 6, 9, 0, tzinfo=timezone.utc).timestamp())
        minutely = self.make_minutely(start_unix=start)
        target = datetime(2026, 4, 6, 9, 15, tzinfo=timezone.utc)
        assert _find_slot(minutely, target) == 1

    def test_rounds_to_nearest_slot(self):
        start = int(datetime(2026, 4, 6, 9, 0, tzinfo=timezone.utc).timestamp())
        minutely = self.make_minutely(start_unix=start)
        # 9:07 → closer to 9:00 (idx 0) than 9:15 (idx 1)
        target = datetime(2026, 4, 6, 9, 7, tzinfo=timezone.utc)
        assert _find_slot(minutely, target) == 0

    def test_clamps_below_zero(self):
        start = int(datetime(2026, 4, 6, 9, 0, tzinfo=timezone.utc).timestamp())
        minutely = self.make_minutely(start_unix=start)
        target = datetime(2026, 4, 6, 8, 0, tzinfo=timezone.utc)  # before start
        assert _find_slot(minutely, target) == 0

    def test_clamps_above_max(self):
        start = int(datetime(2026, 4, 6, 9, 0, tzinfo=timezone.utc).timestamp())
        minutely = self.make_minutely(start_unix=start, n_steps=4)
        target = datetime(2026, 4, 6, 23, 0, tzinfo=timezone.utc)  # far after end
        assert _find_slot(minutely, target) == 3  # last valid index


# --- _parse_responses ---

class TestParseResponses:
    def setup_method(self):
        self.coords = make_coords((48.0, 11.0), (48.5, 11.5))
        self.arrival_times = make_arrival_times(9, 10)

    def test_returns_list_of_snapshots(self):
        responses = [make_mock_response(48.0, 11.0)]
        result = _parse_responses(responses, [self.coords[0]], [self.arrival_times[0]])
        assert isinstance(result, list)
        assert all(isinstance(s, WeatherSnapshot) for s in result)

    def test_one_snapshot_per_coordinate(self):
        responses = [
            make_mock_response(48.0, 11.0),
            make_mock_response(48.5, 11.5),
        ]
        result = _parse_responses(responses, self.coords, self.arrival_times)
        assert len(result) == 2

    def test_snapshot_coords_match(self):
        responses = [make_mock_response(48.0, 11.0)]
        result = _parse_responses(responses, [self.coords[0]], [self.arrival_times[0]])
        assert result[0].coords == self.coords[0]

    def test_snapshot_timestamp_matches_arrival(self):
        responses = [make_mock_response(48.0, 11.0)]
        result = _parse_responses(responses, [self.coords[0]], [self.arrival_times[0]])
        assert result[0].timestamp == self.arrival_times[0]

    def test_snapshot_has_wind_speed(self):
        responses = [make_mock_response(48.0, 11.0)]
        result = _parse_responses(responses, [self.coords[0]], [self.arrival_times[0]])
        assert isinstance(result[0].wind_speed_km_h, float)

    def test_snapshot_has_wind_direction(self):
        responses = [make_mock_response(48.0, 11.0)]
        result = _parse_responses(responses, [self.coords[0]], [self.arrival_times[0]])
        assert isinstance(result[0].wind_direction_deg, float)

    def test_snapshot_has_gusts(self):
        responses = [make_mock_response(48.0, 11.0)]
        result = _parse_responses(responses, [self.coords[0]], [self.arrival_times[0]])
        assert isinstance(result[0].wind_gusts_km_h, float)

    def test_snapshot_has_precipitation(self):
        responses = [make_mock_response(48.0, 11.0)]
        result = _parse_responses(responses, [self.coords[0]], [self.arrival_times[0]])
        assert isinstance(result[0].precipitation_mm_h, float)


# --- get_weather ---

class TestGetWeather:
    def setup_method(self):
        self.coords = make_coords((48.0, 11.0), (48.5, 11.5))
        self.arrival_times = make_arrival_times(9, 10)

    @patch("app.services.weather.openmeteo_requests.Client")
    def test_returns_list_of_snapshots(self, mock_client_cls):
        mock_client_cls.return_value.weather_api.return_value = [
            make_mock_response(48.0, 11.0),
            make_mock_response(48.5, 11.5),
        ]
        result = get_weather(self.coords, self.arrival_times)
        assert isinstance(result, list)
        assert len(result) == 2

    @patch("app.services.weather.openmeteo_requests.Client")
    def test_correct_number_of_snapshots(self, mock_client_cls):
        mock_client_cls.return_value.weather_api.return_value = [
            make_mock_response(48.0, 11.0),
        ]
        result = get_weather([self.coords[0]], [self.arrival_times[0]])
        assert len(result) == 1

    @patch("app.services.weather.openmeteo_requests.Client")
    def test_api_called_with_correct_coordinates(self, mock_client_cls):
        mock_client = MagicMock()
        mock_client.weather_api.return_value = [make_mock_response(48.0, 11.0)]
        mock_client_cls.return_value = mock_client

        get_weather([self.coords[0]], [self.arrival_times[0]])

        params = mock_client.weather_api.call_args.kwargs["params"]
        assert params["latitude"] == [48.0]
        assert params["longitude"] == [11.0]

    @patch("app.services.weather.openmeteo_requests.Client")
    def test_api_called_with_correct_date_range(self, mock_client_cls):
        mock_client = MagicMock()
        mock_client.weather_api.return_value = [make_mock_response(48.0, 11.0)]
        mock_client_cls.return_value = mock_client

        get_weather([self.coords[0]], [self.arrival_times[0]])

        params = mock_client.weather_api.call_args.kwargs["params"]
        assert params["start_date"] == "2026-04-06"
        assert params["end_date"] == "2026-04-06"