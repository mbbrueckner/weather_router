"""Tests for app/services/route_scorer.py"""

import math
import pytest
from app.services.route_scorer import (
    _deg_to_vector,
    _invert_wind_direction,
    _mm_15_to_mm_h,
    _categorize_wind_alignment,
    score_segment,
    WindAlignment,
    MAX_GUST_SPEED_KM_H,
    MAX_GUST_DELTA_KM_H,
    MAX_PRECIPITATION_MM_H,
    MAX_TAILWIND_SPEED_KM_H,
    MAX_HEADWIND_SPEED_KM_H,
    MAX_CROSSWIND_SPEED_KM_H,
)


# ── _invert_wind_direction ────────────────────────────────────────

def test_invert_wind_direction_basic():
    assert _invert_wind_direction(0.0) == 180.0

def test_invert_wind_direction_wraps():
    assert _invert_wind_direction(270.0) == 90.0

def test_invert_wind_direction_full_circle():
    assert _invert_wind_direction(180.0) == 0.0

def test_invert_wind_direction_no_negative():
    """Result should always be in 0–360, never negative."""
    assert 0.0 <= _invert_wind_direction(0.0) < 360.0
    assert 0.0 <= _invert_wind_direction(359.0) < 360.0


# ── _deg_to_vector ────────────────────────────────────────────────

def test_deg_to_vector_north():
    x, y = _deg_to_vector(0.0)
    assert math.isclose(x, 0.0, abs_tol=1e-9)
    assert math.isclose(y, 1.0, abs_tol=1e-9)

def test_deg_to_vector_east():
    x, y = _deg_to_vector(90.0)
    assert math.isclose(x, 1.0, abs_tol=1e-9)
    assert math.isclose(y, 0.0, abs_tol=1e-9)

def test_deg_to_vector_south():
    x, y = _deg_to_vector(180.0)
    assert math.isclose(x, 0.0, abs_tol=1e-9)
    assert math.isclose(y, -1.0, abs_tol=1e-9)

def test_deg_to_vector_west():
    x, y = _deg_to_vector(270.0)
    assert math.isclose(x, -1.0, abs_tol=1e-9)
    assert math.isclose(y, 0.0, abs_tol=1e-9)

def test_deg_to_vector_unit_length():
    """All vectors must have length 1.0."""
    for deg in [0, 45, 90, 135, 180, 225, 270, 315]:
        x, y = _deg_to_vector(float(deg))
        assert math.isclose(x**2 + y**2, 1.0, abs_tol=1e-9)


# ── _mm_15_to_mm_h ────────────────────────────────────────────────

def test_mm_15_to_mm_h():
    assert _mm_15_to_mm_h(5.0) == 20.0

def test_mm_15_to_mm_h_zero():
    assert _mm_15_to_mm_h(0.0) == 0.0

def test_mm_15_to_mm_h_factor():
    """Conversion factor must always be exactly 4."""
    for val in [0.1, 1.0, 2.5, 10.0]:
        assert math.isclose(_mm_15_to_mm_h(val), val * 4.0)


# ── _categorize_wind_alignment ────────────────────────────────────

def test_categorize_tailwind():
    assert _categorize_wind_alignment(0.6) == WindAlignment.TAILWIND

def test_categorize_headwind():
    assert _categorize_wind_alignment(-0.6) == WindAlignment.HEADWIND

def test_categorize_crosswind():
    assert _categorize_wind_alignment(0.0) == WindAlignment.CROSSWIND

def test_categorize_boundary_tailwind():
    """Exactly 0.5 is still crosswind, above is tailwind."""
    assert _categorize_wind_alignment(0.5) == WindAlignment.CROSSWIND
    assert _categorize_wind_alignment(0.51) == WindAlignment.TAILWIND

def test_categorize_boundary_headwind():
    """Exactly -0.5 is still crosswind, below is headwind."""
    assert _categorize_wind_alignment(-0.5) == WindAlignment.CROSSWIND
    assert _categorize_wind_alignment(-0.51) == WindAlignment.HEADWIND


# ── dot product logic ─────────────────────────────────────────────

def test_wind_alignment_tailwind():
    """Wind blowing in the same direction as travel → dot close to +1."""
    bx, by = _deg_to_vector(0.0)
    wx, wy = _deg_to_vector(_invert_wind_direction(180.0))
    dot = bx*wx + by*wy
    assert math.isclose(dot, 1.0, abs_tol=1e-9)

def test_wind_alignment_headwind():
    """Wind blowing against travel direction → dot close to -1."""
    bx, by = _deg_to_vector(0.0)
    wx, wy = _deg_to_vector(_invert_wind_direction(0.0))
    dot = bx*wx + by*wy
    assert math.isclose(dot, -1.0, abs_tol=1e-9)

def test_wind_alignment_crosswind():
    """Wind blowing perpendicular to travel → dot close to 0."""
    bx, by = _deg_to_vector(0.0)
    wx, wy = _deg_to_vector(_invert_wind_direction(90.0))
    dot = bx*wx + by*wy
    assert math.isclose(dot, 0.0, abs_tol=1e-9)


# ── score_segment: Normalfälle ────────────────────────────────────

def test_perfect_tailwind_scores_positive():
    """Wind from west, riding east → pure tailwind → positive score."""
    score = score_segment(
        wind_speed_km_h=20.0,
        wind_direction_deg=270.0,
        gust_speed_km_h=5.0,
        precipitation_mm_15=0.0,
        bearing_deg=90.0,
    )
    assert score > 0.0

def test_perfect_headwind_scores_negative():
    """Wind from east, riding east → pure headwind → negative score."""
    score = score_segment(
        wind_speed_km_h=20.0,
        wind_direction_deg=90.0,
        gust_speed_km_h=5.0,
        precipitation_mm_15=0.0,
        bearing_deg=90.0,
    )
    assert score < 0.0

def test_crosswind_scores_near_zero():
    """Wind from north, riding east → crosswind → score near zero."""
    score = score_segment(
        wind_speed_km_h=20.0,
        wind_direction_deg=0.0,
        gust_speed_km_h=5.0,
        precipitation_mm_15=0.0,
        bearing_deg=90.0,
    )
    assert -0.3 < score < 0.3

def test_zero_wind_scores_zero():
    """No wind, no rain, no gusts → neutral score."""
    score = score_segment(
        wind_speed_km_h=0.0,
        wind_direction_deg=270.0,
        gust_speed_km_h=0.0,
        precipitation_mm_15=0.0,
        bearing_deg=90.0,
    )
    assert math.isclose(score, 0.0, abs_tol=1e-9)

def test_score_always_within_bounds():
    """Score must never exceed -1.0 to +1.0 for any input combination."""
    for wind_dir in range(0, 360, 45):
        for speed in [0.0, 10.0, 25.0, 49.0]:
            score = score_segment(
                wind_speed_km_h=speed,
                wind_direction_deg=float(wind_dir),
                gust_speed_km_h=min(speed + 5.0, MAX_GUST_SPEED_KM_H - 1),
                precipitation_mm_15=0.0,
                bearing_deg=90.0,
            )
            assert -1.0 <= score <= 1.0, (
                f"Score {score} out of bounds for wind_dir={wind_dir}, speed={speed}"
            )


# ── score_segment: Hard Blocks ────────────────────────────────────

def test_excessive_gusts_returns_hard_block():
    score = score_segment(
        wind_speed_km_h=10.0,
        wind_direction_deg=270.0,
        gust_speed_km_h=MAX_GUST_SPEED_KM_H + 1.0,
        precipitation_mm_15=0.0,
        bearing_deg=90.0,
    )
    assert score == -1.0

def test_excessive_gust_delta_returns_hard_block():
    """Gusts much stronger than average wind → unpredictable → hard block."""
    score = score_segment(
        wind_speed_km_h=5.0,
        wind_direction_deg=270.0,
        gust_speed_km_h=5.0 + MAX_GUST_DELTA_KM_H + 1.0,
        precipitation_mm_15=0.0,
        bearing_deg=90.0,
    )
    assert score == -1.0

def test_heavy_rain_returns_hard_block():
    """Precipitation exceeding threshold → hard block."""
    mm_15_threshold = (MAX_PRECIPITATION_MM_H / 4.0) + 0.1
    score = score_segment(
        wind_speed_km_h=10.0,
        wind_direction_deg=270.0,
        gust_speed_km_h=5.0,
        precipitation_mm_15=mm_15_threshold,
        bearing_deg=90.0,
    )
    assert score == -1.0

def test_excessive_tailwind_returns_hard_block():
    score = score_segment(
        wind_speed_km_h=MAX_TAILWIND_SPEED_KM_H + 1.0,
        wind_direction_deg=270.0,
        gust_speed_km_h=10.0,
        precipitation_mm_15=0.0,
        bearing_deg=90.0,
    )
    assert score == -1.0

def test_excessive_headwind_returns_hard_block():
    score = score_segment(
        wind_speed_km_h=MAX_HEADWIND_SPEED_KM_H + 1.0,
        wind_direction_deg=90.0,
        gust_speed_km_h=10.0,
        precipitation_mm_15=0.0,
        bearing_deg=90.0,
    )
    assert score == -1.0

def test_excessive_crosswind_returns_hard_block():
    score = score_segment(
        wind_speed_km_h=MAX_CROSSWIND_SPEED_KM_H + 1.0,
        wind_direction_deg=0.0,   # Seitenwind zu Fahrtrichtung Ost
        gust_speed_km_h=10.0,
        precipitation_mm_15=0.0,
        bearing_deg=90.0,
    )
    assert score == -1.0


# ── score_segment: Grenzwerte ─────────────────────────────────────

def test_exactly_at_gust_limit_not_hard_block():
    """Exactly at the limit should NOT trigger hard block."""
    score = score_segment(
        wind_speed_km_h=10.0,
        wind_direction_deg=270.0,
        gust_speed_km_h=MAX_GUST_SPEED_KM_H,
        precipitation_mm_15=0.0,
        bearing_deg=90.0,
    )
    assert score != -1.0

def test_rain_and_headwind_both_penalize():
    """Rain + headwind should score worse than headwind alone."""
    headwind_only = score_segment(10.0, 90.0, 5.0, 0.0, 90.0)
    headwind_rain  = score_segment(10.0, 90.0, 5.0, 1.0, 90.0)
    assert headwind_rain < headwind_only