"""Tests for app/services/route_scorer.py"""

import math
import pytest

from app.services.route_scorer import (
    _deg_to_vector,
    _invert_wind_direction,
    _mm_15_to_mm_h,
)


# --- _invert_wind_direction ---

def test_invert_wind_direction_basic():
    assert _invert_wind_direction(0.0) == 180.0

def test_invert_wind_direction_wraps():
    assert _invert_wind_direction(270.0) == 90.0

def test_invert_wind_direction_full_circle():
    assert _invert_wind_direction(180.0) == 0.0


# --- _deg_to_vector ---

def test_deg_to_vector_north():
    x, y = _deg_to_vector(0.0)
    assert math.isclose(x, 1.0, abs_tol=1e-9)
    assert math.isclose(y, 0.0, abs_tol=1e-9)

def test_deg_to_vector_unit_length():
    for deg in [0, 45, 90, 135, 180, 270]:
        x, y = _deg_to_vector(float(deg))
        assert math.isclose(x**2 + y**2, 1.0, abs_tol=1e-9)


# --- _mm_15_to_mm_h ---

def test_mm_15_to_mm_h():
    assert _mm_15_to_mm_h(5.0) == 20.0

def test_mm_15_to_mm_h_zero():
    assert _mm_15_to_mm_h(0.0) == 0.0


# --- wind_alignment (dot product logic) ---

def test_wind_alignment_tailwind():
    """Wind blowing in the same direction as travel → alignment close to 1."""
    bearing = 0.0
    wind_from = 180.0  # wind comes from behind (south), blowing north
    bx, by = _deg_to_vector(bearing)
    wx, wy = _deg_to_vector(_invert_wind_direction(wind_from))
    dot = bx * wx + by * wy
    assert math.isclose(dot, 1.0, abs_tol=1e-9)

def test_wind_alignment_headwind():
    """Wind blowing against travel direction → alignment close to -1."""
    bearing = 0.0
    wind_from = bearing  # wind comes from the front
    bx, by = _deg_to_vector(bearing)
    wx, wy = _deg_to_vector(_invert_wind_direction(wind_from))
    dot = bx * wx + by * wy
    assert math.isclose(dot, -1.0, abs_tol=1e-9)

def test_wind_alignment_crosswind():
    """Wind blowing perpendicular to travel → alignment close to 0."""
    bearing = 0.0
    wind_from = 90.0  # wind from the side
    bx, by = _deg_to_vector(bearing)
    wx, wy = _deg_to_vector(_invert_wind_direction(wind_from))
    dot = bx * wx + by * wy
    assert math.isclose(dot, 0.0, abs_tol=1e-9)
