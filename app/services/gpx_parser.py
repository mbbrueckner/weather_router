"""GPX file parsing and route segmentation.

This module provides functionality to parse GPX files and extract route points, as well as to split the route into segments with calculated bearings and distances.
"""

__author__ = "mbbrueckner"
__version__ = "1.1.0"


from datetime import datetime, timedelta

from app.models import ClusteredRoute, RoutePoint, Segment, SegmentCluster

from rdp import rdp

import gpxpy
import math
import numpy as np

EARTH_RADIUS = 6_371_000
EPSILON = 0.0005
SLOT_MIN = 15.0
MAX_BEARING_DIFF_DEG = 30.0
MIN_CLUSTER_DISTANCE_M = 750


# --- Main Functions ---

def get_clustered_route(file_content: bytes, avg_speed_kmh: float, start_time: datetime) -> ClusteredRoute:
    """Parse GPX file content and extract route clusters.

    Combines the main steps of parsing, segmenting, and clustering into a single function.

    Args:
        file_content: Raw bytes of a GPX file.
        avg_speed_kmh: Rider's average speed in km/h, used for dynamic cluster sizing.
        start_time: The start time for weather data retrieval.
    Returns:
        ClusteredRoute containing all SegmentClusters representing straight portions of the route.
    """
    points = parse_gpx(file_content)
    segments = split_into_segments(points)
    clusters = cluster_segments(segments, avg_speed_kmh, start_time)
    return ClusteredRoute(clusters=clusters)


def parse_gpx(file_content: bytes) -> list[RoutePoint]:
    """Parse a GPX file and extract an ordered list of descriptive RoutePoints.

    Iterates over all tracks and segments in the GPX data and collects
    each point as a RoutePoint.
    Runs a simplification step to reduce the number of points while preserving the route shape.

    Args:
        file_content: Raw bytes of a GPX file.

    Returns:
        Ordered list of descriptive RoutePoints.
    """
    gpx = gpxpy.parse(file_content)
    points = []
    for track in gpx.tracks:
        for segment in track.segments:
            for p in segment.points:
                points.append(
                    RoutePoint(
                        lat=p.latitude,
                        lon=p.longitude,
                        elevation_m=p.elevation,
                    )
                )
    return _simplify(points)


def split_into_segments(points: list[RoutePoint]) -> list[Segment]:
    """Split an ordered list of RoutePoints into consecutive Segments.

    Args:
        points: Ordered list of RoutePoints representing a route.

    Returns:
        List of Segments, each annotated with bearing and distance.
        Contains len(points) - 1 entries.
    """
    segments = []
    for p1, p2 in zip(points[:-1], points[1:]):
        segments.append(
            Segment(
                start=p1,
                end=p2,
                bearing_deg=_bearing(p1, p2),
                distance_m=_haversine(p1, p2)
            )
        )
    return segments


def cluster_segments(
    segments: list[Segment],
    avg_speed_kmh: float = 20.0,
    start_time: datetime | None = None,
) -> list[SegmentCluster]:
    """Group consecutive segments into clusters based on bearing similarity and distance.

    A new cluster is started whenever the accumulated distance exceeds the
    dynamically computed maximum (based on speed and gradient), or the bearing
    difference to the current cluster exceeds MAX_BEARING_DIFF_DEG.

    Args:
        segments: Ordered list of Segments to cluster.
        avg_speed_kmh: Rider's average speed in km/h, used to compute max cluster size.
        start_time: Start time of the route. If provided, timestamps for representative
            points are computed from cumulative distance and avg_speed_kmh.

    Returns:
        List of SegmentClusters representing straight portions of the route.
    """
    clusters = []
    current_cluster_segments: list[Segment] = []
    current_cluster_length: float = 0.0
    current_cluster_bearing: float = 0.0
    cumulative_time_s: float = 0.0

    for seg in segments:
        segment_length = seg.distance_m
        segment_bearing = seg.bearing_deg

        if not current_cluster_segments:
            current_cluster_segments.append(seg)
            current_cluster_length = segment_length
            current_cluster_bearing = segment_bearing

        else:
            new_length = current_cluster_length + segment_length
            bearing_difference = _unsigned_bearing_difference(current_cluster_bearing, segment_bearing)

            gradient = _cluster_gradient(current_cluster_segments)
            max_distance = _max_cluster_distance(avg_speed_kmh, gradient)

            should_continue = (
                new_length < max_distance
                and (current_cluster_length < MIN_CLUSTER_DISTANCE_M or bearing_difference < MAX_BEARING_DIFF_DEG)
            )

            if should_continue:
                current_cluster_segments.append(seg)
                current_cluster_length += segment_length

                sin_sum = sum(math.sin(math.radians(s.bearing_deg)) for s in current_cluster_segments)
                cos_sum = sum(math.cos(math.radians(s.bearing_deg)) for s in current_cluster_segments)
                current_cluster_bearing = math.degrees(math.atan2(sin_sum, cos_sum)) % 360
            else:
                gradient = _cluster_gradient(current_cluster_segments)
                cluster_speed_m_per_s = _estimate_speed(avg_speed_kmh, gradient) * 1000.0 / 3600.0
                timestamp = _cluster_timestamp(start_time, cumulative_time_s, current_cluster_length, cluster_speed_m_per_s)
                clusters.append(_build_cluster(current_cluster_segments, current_cluster_bearing, timestamp))
                cumulative_time_s += current_cluster_length / cluster_speed_m_per_s
                current_cluster_segments = [seg]
                current_cluster_length = segment_length
                current_cluster_bearing = segment_bearing

    if current_cluster_segments:
        gradient = _cluster_gradient(current_cluster_segments)
        cluster_speed_m_per_s = _estimate_speed(avg_speed_kmh, gradient) * 1000.0 / 3600.0
        timestamp = _cluster_timestamp(start_time, cumulative_time_s, current_cluster_length, cluster_speed_m_per_s)
        clusters.append(_build_cluster(current_cluster_segments, current_cluster_bearing, timestamp))

    return clusters


def write_gpx(points: list[RoutePoint]) -> bytes:
    """Serialize a list of RoutePoints to GPX file content.

    Args:
        points: Ordered list of RoutePoints representing a route.

    Returns:
        GPX file content as bytes.
    """
    gpx = gpxpy.gpx.GPX()
    track = gpxpy.gpx.GPXTrack()
    gpx.tracks.append(track)
    segment = gpxpy.gpx.GPXTrackSegment()
    track.segments.append(segment)
    for p in points:
        segment.points.append(
            gpxpy.gpx.GPXTrackPoint(
                latitude=p.lat,
                longitude=p.lon,
                elevation=p.elevation_m,
                time=p.timestamp,
            )
        )
    return gpx.to_xml().encode()


# --- Helper Functions ---

def _simplify(points: list[RoutePoint]) -> list[RoutePoint]:
    """Simplify a list of RoutePoints using the Ramer-Douglas-Peucker algorithm.

    Args:
        points: List of RoutePoints to simplify.

    Returns:
        Simplified list of RoutePoints.
    """
    coords = np.array([[p.lat, p.lon] for p in points])
    mask = rdp(coords, epsilon=EPSILON, return_mask=True)
    return [p for p, keep in zip(points, mask) if keep]


def _max_cluster_distance(avg_speed_kmh: float, gradient_pct: float = 0.0) -> float:
    """Compute the maximum cluster distance for one weather slot.

    Args:
        avg_speed_kmh: Rider's base average speed in km/h.
        gradient_pct: Current gradient in percent (positive = uphill).

    Returns:
        Maximum cluster distance in meters.
    """
    local_speed = _estimate_speed(avg_speed_kmh, gradient_pct)
    return (local_speed / 60.0) * SLOT_MIN * 1000.0


def _estimate_speed(base_speed_kmh: float, gradient_pct: float) -> float:
    """Estimate local riding speed based on gradient.

    Applies a simple linear model: each percent of gradient
    reduces speed by 1.5 km/h (negative gradient increases it).

    Args:
        base_speed_kmh: Rider's base average speed in km/h.
        gradient_pct: Gradient in percent (positive = uphill, negative = downhill).

    Returns:
        Estimated local speed in km/h, clamped to 5–60 km/h.
    """
    speed = base_speed_kmh - gradient_pct * 1.5
    return max(5.0, min(60.0, speed))


def _cluster_gradient(segments: list[Segment]) -> float:
    """Compute the overall gradient of a list of segments in percent.

    Uses the elevation of the first start point and last end point.
    Returns 0.0 if elevation data is unavailable.

    Args:
        segments: Non-empty list of Segments.

    Returns:
        Gradient in percent (positive = uphill, negative = downhill).
    """
    start_elev = segments[0].start.elevation_m
    end_elev = segments[-1].end.elevation_m
    if start_elev is None or end_elev is None:
        return 0.0
    total_distance = sum(s.distance_m for s in segments)
    if total_distance == 0.0:
        return 0.0
    return ((end_elev - start_elev) / total_distance) * 100.0


def _haversine(p1: RoutePoint, p2: RoutePoint) -> float:
    """Calculate the great-circle distance between two points using the Haversine formula.

    Args:
        p1: Starting point.
        p2: Ending point.

    Returns:
        Distance in meters.
    """
    phi_1, phi_2 = math.radians(p1.lat), math.radians(p2.lat)
    d_phi = math.radians(p2.lat - p1.lat)
    d_lam = math.radians(p2.lon - p1.lon)
    a = math.sin(d_phi/2)**2 + math.cos(phi_1) * math.cos(phi_2) * math.sin(d_lam/2)**2
    return EARTH_RADIUS * 2 * math.asin(math.sqrt(a))


def _bearing(p1: RoutePoint, p2: RoutePoint) -> float:
    """Calculate the initial bearing from p1 to p2.

    Args:
        p1: Starting point.
        p2: Ending point.

    Returns:
        Bearing in degrees, clockwise from north (0–360).
    """
    phi_1, phi_2 = math.radians(p1.lat), math.radians(p2.lat)
    lam_1, lam_2 = math.radians(p1.lon), math.radians(p2.lon)
    y = math.sin(lam_2 - lam_1) * math.cos(phi_2)
    x = math.cos(phi_1) * math.sin(phi_2) - math.sin(phi_1) * math.cos(phi_2) * math.cos(lam_2 - lam_1)
    return (math.degrees(math.atan2(y, x)) + 360) % 360


def _cluster_timestamp(
    start_time: datetime | None,
    cumulative_time_s: float,
    cluster_length_m: float,
    speed_m_per_s: float,
) -> datetime | None:
    """Compute the timestamp for the midpoint of a cluster.

    Args:
        start_time: Route start time, or None if unavailable.
        cumulative_time_s: Elapsed seconds from route start to the beginning of this cluster.
        cluster_length_m: Total length of the cluster in meters.
        speed_m_per_s: Gradient-adjusted rider speed for this cluster in m/s.

    Returns:
        Datetime of the cluster midpoint, or None if start_time is None.
    """
    if start_time is None or speed_m_per_s == 0.0:
        return None
    elapsed_s = cumulative_time_s + (cluster_length_m / 2.0) / speed_m_per_s
    return start_time + timedelta(seconds=elapsed_s)


def _build_cluster(segments: list[Segment], mean_bearing: float, timestamp: datetime | None = None) -> SegmentCluster:
    """Build a SegmentCluster from a list of segments.

    The representative point is the geographic midpoint of the middle segment.

    Args:
        segments: Non-empty list of Segments belonging to this cluster.
        mean_bearing: Average bearing of the segments in degrees (0–360).
        timestamp: Precomputed timestamp for the representative point.

    Returns:
        A SegmentCluster representing the group.
    """
    num_segments = len(segments)
    middle_segment = segments[num_segments // 2]

    start_elev = middle_segment.start.elevation_m
    end_elev = middle_segment.end.elevation_m

    representative_point = RoutePoint(
        lat=(middle_segment.start.lat + middle_segment.end.lat) / 2,
        lon=(middle_segment.start.lon + middle_segment.end.lon) / 2,
        elevation_m=(
            (start_elev + end_elev) / 2
            if (start_elev is not None and end_elev is not None)
            else None
        ),
        timestamp=timestamp,
    )

    return SegmentCluster(
        segments=segments,
        mean_bearing=mean_bearing,
        representative_point=representative_point,
    )


def _signed_bearing_difference(b1: float, b2: float) -> float:
    """Calculate the signed difference between two bearings.

    Args:
        b1: First bearing in degrees.
        b2: Second bearing in degrees.

    Returns:
        Signed difference in degrees, in the range (-180, 180].
    """
    diff = (b2 - b1) % 360
    if diff > 180:
        diff -= 360
    return diff


def _unsigned_bearing_difference(b1: float, b2: float) -> float:
    """Calculate the unsigned difference between two bearings.

    Args:
        b1: First bearing in degrees.
        b2: Second bearing in degrees.

    Returns:
        Unsigned difference in degrees, in the range [0, 180].
    """
    diff = abs(b1 - b2) % 360
    return min(diff, 360 - diff)