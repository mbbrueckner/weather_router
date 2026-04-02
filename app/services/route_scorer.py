"""Route scoring based on weather conditions.

This module scores route segments by combining wind alignment, gust intensity,
and precipitation into a single float score.
"""

__author__ = "mbbrueckner"
__version__ = "1.0.0"

import math
from enum import Enum
from app.models import Segment

MAX_HEADWIND_SPEED_KMH = 60.0
MAX_TAILWIND_SPEED_KMH = 50.0
MAX_CROSSWIND_SPEED_KMH = 50.0

MAX_GUST_SPEED_KMH = 20.0
MAX_GUST_DELTA_KMH = 10.0

MAX_PRECIPITATION_MM_H = 20.0


class WindAlignment(Enum):
    HEADWIND = -1
    CROSSWIND = 0
    TAILWIND = 1

def score_segment(
    wind_speed_ms: float,
    wind_direction_deg: float,
    gust_speed_ms: float,
    precipitation_mm_15: float,
    bearing_deg: float,
) -> float:
    """Score a route segment based on current weather conditions.

    Returns a score between -1.0 (unrideable) and 1.0 (ideal).
    Returns -1.0 immediately if any condition exceeds its defined maximum.

    Args:
        wind_speed_ms: Wind speed in m/s.
        wind_direction_deg: Wind direction in degrees (meteorological: direction the wind comes from).
        gust_speed_ms: Gust speed in m/s.
        precipitation_mm_15: Precipitation in the last 15 minutes in mm.
        bearing_deg: Travel direction of the segment in degrees.

    Returns:
        Score between -1.0 and 1.0.
    """

    gust_delta = gust_speed_ms - wind_speed_ms
    precipitation_mmh = precipitation_mm_15 * 4.0

    if gust_speed_ms > MAX_GUST_SPEED_MS:       return -1.0
    if gust_delta > MAX_GUST_DELTA_MS:           return -1.0
    if precipitation_mmh > MAX_PRECIPITATION_MMH: return -1.0

    bx, by = _deg_to_vector(bearing_deg)
    wx, wy = _deg_to_vector(_invert_wind_direction(wind_direction_deg))
    dot = bx*wx + by*wy
    wind_score = dot * (wind_speed_ms / WIND_REFERENCE_MS)
    wind_score = max(-1.0, min(1.0, wind_score))

    if dot > 0.5 and wind_speed_ms > MAX_TAILWIND_MS: return -1.0

    gust_score = -min(gust_speed_ms / MAX_GUST_SPEED_MS, 1.0)

    rain_score = -min(precipitation_mmh / MAX_PRECIPITATION_MMH, 1.0)

    return wind_score * 0.5 + gust_score * 0.3 + rain_score * 0.2

def _mm_15_to_mm_h(mm_15: float) -> float:
    """Convert precipitation from mm per 15 minutes to mm per hour.

    Args:
        mm_15: Precipitation in mm over 15 minutes.

    Returns:
        Precipitation in mm/h.
    """
    return mm_15 * 4.0

def _deg_to_vector(deg: float) -> tuple[float, float]:
    """Convert a bearing in degrees to a unit vector.

    Args:
        deg: Bearing in degrees, clockwise from north.

    Returns:
        Unit vector as (x, y) tuple.
    """
    rad = math.radians(deg)
    return math.cos(rad), math.sin(rad)

def _invert_wind_direction(deg: float) -> float:
    """Convert a meteorological wind direction to the direction the wind is blowing towards.

    Args:
        deg: Wind origin direction in degrees (where the wind comes from).

    Returns:
        Wind flow direction in degrees (where the wind is going).
    """
    return (deg + 180) % 360
