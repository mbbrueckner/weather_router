"""GPX file parsing and route segmentation.

This module provides functionality to parse GPX files and extract route points, as well as to split the route into segments with calculated bearings and distances.
"""

__author__ = "mbbrueckner"
__version__ = "1.0.0"


from app.models import RoutePoint, Segment, SegmentCluster

from rdp import rdp

import gpxpy
import math
import numpy as np

EARTH_RADIUS = 6_371_000
EPSILON = 0.0005  
MAX_BEARING_DIFF_DEG = 30.0
MAX_CLUSTER_DISTANCE_M = 7_000
MIN_CLUSTER_DISTANCE_M = 750

# --- Main Functions ---

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
                        timestamp=p.time
                    )
                  )
    return _simplify(points)



def cluster_segments(segments: list[Segment]) -> list[SegmentCluster]:
    """Group consecutive segments into clusters based on bearing similarity and distance.

    A new cluster is started whenever the accumulated distance exceeds
    MAX_CLUSTER_DISTANCE_M or the bearing difference to the current cluster
    exceeds MAX_BEARING_DIFF_DEG.

    Args:
        segments: Ordered list of Segments to cluster.

    Returns:
        List of SegmentClusters representing straight portions of the route.
    """
    clusters = []
    current_cluster_segments: list[Segment] = []
    current_cluster_length: float = 0.0
    current_cluster_bearing: float = 0.0

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

            should_continue = (
                new_length < MAX_CLUSTER_DISTANCE_M
                and (current_cluster_length < MIN_CLUSTER_DISTANCE_M or bearing_difference < MAX_BEARING_DIFF_DEG)
            )

            if should_continue:
                current_cluster_segments.append(seg)
                current_cluster_length += segment_length

                sin_sum = sum(math.sin(math.radians(s.bearing_deg)) for s in current_cluster_segments)
                cos_sum = sum(math.cos(math.radians(s.bearing_deg)) for s in current_cluster_segments)
                current_cluster_bearing = math.degrees(math.atan2(sin_sum, cos_sum)) % 360
            else:
                clusters.append(_build_cluster(current_cluster_segments, current_cluster_bearing))
                current_cluster_segments = [seg]
                current_cluster_length = segment_length
                current_cluster_bearing = segment_bearing

    if current_cluster_segments:
        clusters.append(_build_cluster(current_cluster_segments, current_cluster_bearing))

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
             



def _build_cluster(segments: list[Segment], mean_bearing: float) -> SegmentCluster:
    """Build a SegmentCluster from a list of segments.

    The representative point is the geographic midpoint of the middle segment.
    The mean bearing is computed as a circular mean to correctly handle the
    0°/360° wrap-around.

    Args:
        segments: Non-empty list of Segments belonging to this cluster.
        mean_bearing: Average bearing of the segments in degrees (0–360).
    Returns:
        A SegmentCluster representing the group.
    """
    num_segments = len(segments)

    middle_segment = segments[num_segments // 2]

    start_elev = middle_segment.start.elevation_m
    end_elev = middle_segment.end.elevation_m

    start_ts = middle_segment.start.timestamp
    end_ts = middle_segment.end.timestamp
    timestamp = start_ts + (end_ts - start_ts) / 2 if (start_ts is not None and end_ts is not None) else start_ts

    representative_point = RoutePoint(
        lat=(middle_segment.start.lat + middle_segment.end.lat) / 2,
        lon=(middle_segment.start.lon + middle_segment.end.lon) / 2,
        elevation_m=(start_elev + end_elev) / 2 if (start_elev is not None and end_elev is not None) else None,
        timestamp=timestamp,
    )

    return SegmentCluster(
        segments=segments,
        mean_bearing=mean_bearing,
        representative_point=representative_point,
    )

            
def _signed_bearing_difference(b1: float, b2: float) -> float:
    """ Calculate the signed difference between two bearings

    Args:
        b1: first bearing
        b2: second bearing
    
    Returns:
        Signed difference between b1 and b2
    """
    diff = (b2 - b1) % 360
    if diff > 180:
        diff -= 360
    return diff

def _unsigned_bearing_difference(b1 :float, b2:float) -> float:
    """ Calculate the unsigned difference between two bearings

    Args:
        b1: first bearing
        b2: second bearing
    
    Returns:
        Unsigned difference between b1 and b2
    """
    diff = abs(b1 - b2) % 360
    return min(diff, 360 - diff)
