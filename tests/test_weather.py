"""Tests for app/services/weather.py"""

import pytest
import pandas as pd
from datetime import date
from unittest.mock import MagicMock, patch

from app.models import RoutePoint
from app.services.weather import get_weather, _build_params, _parse_responses, DEFAULT_MINUTELY_15


# --- _build_params ---

class TestBuildParams:
    def setup_method(self):
        self.coords = [
            RoutePoint(lat=48.0, lon=11.0),
            RoutePoint(lat=48.5, lon=11.5),
        ]
        self.start = date(2026, 1, 1)
        self.end = date(2026, 1, 2)

    def test_latitudes(self):
        params = _build_params(self.coords, self.start, self.end, DEFAULT_MINUTELY_15)
        assert params["latitude"] == [48.0, 48.5]

    def test_longitudes(self):
        params = _build_params(self.coords, self.start, self.end, DEFAULT_MINUTELY_15)
        assert params["longitude"] == [11.0, 11.5]

    def test_date_format(self):
        params = _build_params(self.coords, self.start, self.end, DEFAULT_MINUTELY_15)
        assert params["start_date"] == "2026-01-01"
        assert params["end_date"] == "2026-01-02"

    def test_minutely_variables_joined(self):
        params = _build_params(self.coords, self.start, self.end, ["wind_speed_10m", "precipitation"])
        assert params["minutely_15"] == "wind_speed_10m,precipitation"

    def test_wind_speed_unit_ms(self):
        params = _build_params(self.coords, self.start, self.end, DEFAULT_MINUTELY_15)
        assert params["wind_speed_unit"] == "ms"


# --- _parse_responses ---

class TestParseResponses:
    def _make_mock_response(self, lat: float, lon: float, n_steps: int = 4):
        """Build a mock API response object."""
        import numpy as np

        response = MagicMock()
        response.Latitude.return_value = lat
        response.Longitude.return_value = lon

        minutely = MagicMock()
        minutely.Time.return_value = 0          # epoch 0
        minutely.TimeEnd.return_value = n_steps * 900  # 15-min intervals
        minutely.Interval.return_value = 900

        # Each variable returns an array of length n_steps
        def make_variable(values):
            var = MagicMock()
            var.ValuesAsNumpy.return_value = np.array(values, dtype=float)
            return var

        minutely.Variables.side_effect = lambda i: make_variable([float(i)] * n_steps)
        response.Minutely15.return_value = minutely
        return response

    def test_returns_dataframe(self):
        responses = [self._make_mock_response(48.0, 11.0)]
        df = _parse_responses(responses, ["wind_speed_10m"])
        assert isinstance(df, pd.DataFrame)

    def test_columns_present(self):
        variables = ["wind_speed_10m", "precipitation"]
        responses = [self._make_mock_response(48.0, 11.0)]
        df = _parse_responses(responses, variables)
        for col in ["latitude", "longitude", "date"] + variables:
            assert col in df.columns

    def test_multiple_responses_concatenated(self):
        responses = [
            self._make_mock_response(48.0, 11.0, n_steps=4),
            self._make_mock_response(49.0, 12.0, n_steps=4),
        ]
        df = _parse_responses(responses, ["wind_speed_10m"])
        assert len(df) == 8

    def test_lat_lon_values(self):
        responses = [self._make_mock_response(48.123, 11.456)]
        df = _parse_responses(responses, ["wind_speed_10m"])
        assert (df["latitude"] == 48.123).all()
        assert (df["longitude"] == 11.456).all()

    def test_date_column_is_datetime(self):
        responses = [self._make_mock_response(48.0, 11.0)]
        df = _parse_responses(responses, ["wind_speed_10m"])
        assert pd.api.types.is_datetime64_any_dtype(df["date"])


# --- get_weather (integration with mocked API client) ---

class TestGetWeather:
    def _make_mock_response(self, lat=48.0, lon=11.0, n_steps=4):
        import numpy as np

        response = MagicMock()
        response.Latitude.return_value = lat
        response.Longitude.return_value = lon

        minutely = MagicMock()
        minutely.Time.return_value = 0
        minutely.TimeEnd.return_value = n_steps * 900
        minutely.Interval.return_value = 900

        variable = MagicMock()
        variable.ValuesAsNumpy.return_value = np.zeros(n_steps)
        minutely.Variables.return_value = variable
        response.Minutely15.return_value = minutely
        return response

    @patch("app.services.weather.openmeteo_requests.Client")
    def test_end_date_defaults_to_start_date(self, mock_client_cls):
        mock_client = MagicMock()
        mock_client.weather_api.return_value = [self._make_mock_response()]
        mock_client_cls.return_value = mock_client

        coords = [RoutePoint(lat=48.0, lon=11.0)]
        get_weather(coords, start_date=date(2026, 1, 1))

        call_params = mock_client.weather_api.call_args[1]["params"]
        assert call_params["start_date"] == call_params["end_date"] == "2026-01-01"

    @patch("app.services.weather.openmeteo_requests.Client")
    def test_returns_dataframe(self, mock_client_cls):
        mock_client = MagicMock()
        mock_client.weather_api.return_value = [self._make_mock_response()]
        mock_client_cls.return_value = mock_client

        coords = [RoutePoint(lat=48.0, lon=11.0)]
        result = get_weather(coords, start_date=date(2026, 1, 1))
        assert isinstance(result, pd.DataFrame)

    @patch("app.services.weather.openmeteo_requests.Client")
    def test_custom_variables_passed_to_api(self, mock_client_cls):
        mock_client = MagicMock()
        mock_client.weather_api.return_value = [self._make_mock_response()]
        mock_client_cls.return_value = mock_client

        coords = [RoutePoint(lat=48.0, lon=11.0)]
        variables = ["wind_speed_10m", "precipitation"]
        get_weather(coords, start_date=date(2026, 1, 1), minutely_15=variables)

        call_params = mock_client.weather_api.call_args[1]["params"]
        assert call_params["minutely_15"] == "wind_speed_10m,precipitation"
