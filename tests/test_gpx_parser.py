"""Tests for app/services/gpx_parser.py"""

import math
import pytest
from datetime import datetime, timezone

from app.models import RoutePoint, Segment, SegmentCluster
from app.services.gpx_parser import (
    parse_gpx,
    split_into_segments,
    cluster_segments,
    write_gpx,
    _haversine,
    _bearing,
    _signed_bearing_difference,
    _unsigned_bearing_difference,
)


# --- Fixtures ---

def make_gpx_bytes(points: list[tuple]) -> bytes:
    """Build minimal GPX bytes from a list of (lat, lon, ele, time_iso) tuples."""
    trkpts = ""
    for lat, lon, ele, t in points:
        trkpts += f"""
      <trkpt lat="{lat}" lon="{lon}">
        <ele>{ele}</ele>
        <time>{t}</time>
      </trkpt>"""
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<gpx version="1.1" xmlns="http://www.topografix.com/GPX/1/1">
  <trk><trkseg>{trkpts}
  </trkseg></trk>
</gpx>""".encode()


SIMPLE_POINTS = [
    (48.0, 11.0, 500.0, "2026-01-01T10:00:00Z"),
    (48.1, 11.0, 510.0, "2026-01-01T10:10:00Z"),
    (48.2, 11.0, 520.0, "2026-01-01T10:20:00Z"),
    (48.3, 11.0, 530.0, "2026-01-01T10:30:00Z"),
    (48.4, 11.0, 540.0, "2026-01-01T10:40:00Z"),
]


# --- parse_gpx ---

class TestParseGpx:
    def test_returns_route_points(self):
        gpx = make_gpx_bytes(SIMPLE_POINTS)
        points = parse_gpx(gpx)
        assert len(points) >= 2
        assert all(isinstance(p, RoutePoint) for p in points)

    def test_first_and_last_point_preserved(self):
        gpx = make_gpx_bytes(SIMPLE_POINTS)
        points = parse_gpx(gpx)
        assert points[0].lat == pytest.approx(48.0)
        assert points[-1].lat == pytest.approx(48.4)

    def test_simplification_reduces_collinear_points(self):
        # 5 perfectly collinear points should be reduced to 2 (start + end)
        gpx = make_gpx_bytes(SIMPLE_POINTS)
        points = parse_gpx(gpx)
        assert len(points) <= len(SIMPLE_POINTS)

    def test_empty_gpx_returns_empty_list(self):
        empty_gpx = b"""<?xml version="1.0" encoding="UTF-8"?>
<gpx version="1.1" xmlns="http://www.topografix.com/GPX/1/1">
  <trk><trkseg></trkseg></trk>
</gpx>"""
        points = parse_gpx(empty_gpx)
        assert points == []

    def test_timestamps_parsed(self):
        gpx = make_gpx_bytes(SIMPLE_POINTS)
        points = parse_gpx(gpx)
        assert points[0].timestamp is not None


# --- write_gpx / roundtrip ---

class TestWriteGpx:
    def test_roundtrip_preserves_coordinates(self):
        original = [
            RoutePoint(lat=48.0, lon=11.0, elevation_m=500.0),
            RoutePoint(lat=48.5, lon=11.5, elevation_m=600.0),
        ]
        gpx_bytes = write_gpx(original)
        parsed = parse_gpx(gpx_bytes)
        assert len(parsed) == 2
        assert parsed[0].lat == pytest.approx(48.0)
        assert parsed[1].lat == pytest.approx(48.5)

    def test_returns_bytes(self):
        points = [RoutePoint(lat=48.0, lon=11.0)]
        result = write_gpx(points)
        assert isinstance(result, bytes)


# --- split_into_segments ---

class TestSplitIntoSegments:
    def test_segment_count(self):
        points = [RoutePoint(lat=48.0 + i * 0.1, lon=11.0) for i in range(5)]
        segments = split_into_segments(points)
        assert len(segments) == 4

    def test_segment_types(self):
        points = [RoutePoint(lat=48.0 + i * 0.1, lon=11.0) for i in range(3)]
        segments = split_into_segments(points)
        assert all(isinstance(s, Segment) for s in segments)

    def test_single_point_returns_empty(self):
        segments = split_into_segments([RoutePoint(lat=48.0, lon=11.0)])
        assert segments == []

    def test_bearing_northward(self):
        p1 = RoutePoint(lat=48.0, lon=11.0)
        p2 = RoutePoint(lat=49.0, lon=11.0)
        segments = split_into_segments([p1, p2])
        assert segments[0].bearing_deg == pytest.approx(0.0, abs=1.0)

    def test_bearing_eastward(self):
        p1 = RoutePoint(lat=48.0, lon=11.0)
        p2 = RoutePoint(lat=48.0, lon=12.0)
        segments = split_into_segments([p1, p2])
        assert segments[0].bearing_deg == pytest.approx(90.0, abs=1.0)

    def test_distance_positive(self):
        p1 = RoutePoint(lat=48.0, lon=11.0)
        p2 = RoutePoint(lat=48.1, lon=11.0)
        segments = split_into_segments([p1, p2])
        assert segments[0].distance_m > 0


# --- _haversine ---

class TestHaversine:
    def test_same_point_is_zero(self):
        p = RoutePoint(lat=48.0, lon=11.0)
        assert _haversine(p, p) == pytest.approx(0.0)

    def test_known_distance(self):
        # Munich to roughly 1 degree north (~111 km)
        p1 = RoutePoint(lat=48.0, lon=11.0)
        p2 = RoutePoint(lat=49.0, lon=11.0)
        dist = _haversine(p1, p2)
        assert dist == pytest.approx(111_195, rel=0.01)


# --- _bearing ---

class TestBearing:
    def test_north(self):
        p1 = RoutePoint(lat=48.0, lon=11.0)
        p2 = RoutePoint(lat=49.0, lon=11.0)
        assert _bearing(p1, p2) == pytest.approx(0.0, abs=1.0)

    def test_east(self):
        p1 = RoutePoint(lat=48.0, lon=11.0)
        p2 = RoutePoint(lat=48.0, lon=12.0)
        assert _bearing(p1, p2) == pytest.approx(90.0, abs=1.0)

    def test_south(self):
        p1 = RoutePoint(lat=49.0, lon=11.0)
        p2 = RoutePoint(lat=48.0, lon=11.0)
        assert _bearing(p1, p2) == pytest.approx(180.0, abs=1.0)

    def test_west(self):
        p1 = RoutePoint(lat=48.0, lon=12.0)
        p2 = RoutePoint(lat=48.0, lon=11.0)
        assert _bearing(p1, p2) == pytest.approx(270.0, abs=1.0)

    def test_result_in_range(self):
        p1 = RoutePoint(lat=48.0, lon=11.0)
        p2 = RoutePoint(lat=47.5, lon=10.5)
        b = _bearing(p1, p2)
        assert 0.0 <= b < 360.0


# --- bearing difference helpers ---

class TestBearingDifferences:
    def test_unsigned_zero(self):
        assert _unsigned_bearing_difference(90.0, 90.0) == pytest.approx(0.0)

    def test_unsigned_wrap(self):
        assert _unsigned_bearing_difference(350.0, 10.0) == pytest.approx(20.0)

    def test_unsigned_always_positive(self):
        assert _unsigned_bearing_difference(270.0, 90.0) == pytest.approx(180.0)

    def test_signed_positive(self):
        assert _signed_bearing_difference(10.0, 30.0) == pytest.approx(20.0)

    def test_signed_negative(self):
        assert _signed_bearing_difference(30.0, 10.0) == pytest.approx(-20.0)

    def test_signed_wrap_positive(self):
        assert _signed_bearing_difference(350.0, 10.0) == pytest.approx(20.0)

    def test_signed_wrap_negative(self):
        assert _signed_bearing_difference(10.0, 350.0) == pytest.approx(-20.0)


# --- cluster_segments ---

class TestClusterSegments:
    def _make_segments(self, bearings_and_distances: list[tuple]) -> list[Segment]:
        """Build a list of Segments from (bearing, distance_m) tuples."""
        segments = []
        lat = 48.0
        for bearing, dist in bearings_and_distances:
            p1 = RoutePoint(lat=lat, lon=11.0)
            p2 = RoutePoint(lat=lat + 0.001, lon=11.0)
            segments.append(Segment(start=p1, end=p2, bearing_deg=bearing, distance_m=dist))
            lat += 0.001
        return segments

    def test_returns_clusters(self):
        segs = self._make_segments([(0.0, 500)] * 5)
        clusters = cluster_segments(segs)
        assert len(clusters) >= 1
        assert all(isinstance(c, SegmentCluster) for c in clusters)

    def test_empty_input(self):
        assert cluster_segments([]) == []

    def test_large_bearing_change_splits_cluster(self):
        # First group: heading north, second group: heading east — should split
        segs = self._make_segments([(0.0, 1000)] * 3 + [(90.0, 1000)] * 3)
        clusters = cluster_segments(segs)
        assert len(clusters) >= 2

    def test_similar_bearings_stay_together(self):
        segs = self._make_segments([(0.0, 500), (5.0, 500), (355.0, 500)])
        clusters = cluster_segments(segs)
        assert len(clusters) == 1

    def test_representative_point_exists(self):
        segs = self._make_segments([(45.0, 800)] * 4)
        clusters = cluster_segments(segs)
        assert clusters[0].representative_point is not None
        assert isinstance(clusters[0].representative_point, RoutePoint)
