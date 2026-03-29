"""GPX file parsing and route segmentation.

This module provides functionality to parse GPX files and extract route points, as well as to split the route into segments with calculated bearings and distances.
"""

__author__ = "mbbrueckner"
__version__ = "0.1.0"

from datetime import datetime
from dataclasses import dataclass

import gpxpy
import math

# Earth radius in meters
EARTH_RADIUS = 6_371_000

@dataclass
class RoutePoint:
    """A single point along a GPS route.

    Attributes:
        lat: Latitude in decimal degrees.
        lon: Longitude in decimal degrees.
        elevation_m: Elevation above sea level in meters, if available.
        timestamp: UTC timestamp of the recorded point, if available.
    """

    lat: float
    lon: float
    elevation_m: float | None = None
    timestamp: datetime | None = None

def parse_gpx(file_content: bytes) -> list[RoutePoint]:
    """Parse a GPX file and extract all track points.

    Iterates over all tracks and segments in the GPX data and collects
    each point as a RoutePoint.

    Args:
        file_content: Raw bytes of a GPX file.

    Returns:
        Ordered list of RoutePoints from all tracks and segments.
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
    return points



@dataclass
class Segment:
    """A route segment between two consecutive RoutePoints.

    Attributes:
        start: Starting point of the segment.
        end: Ending point of the segment.
        bearing_deg: Initial bearing from start to end in degrees (0–360).
        distance_m: Great-circle distance from start to end in meters.
    """

    start: RoutePoint
    end: RoutePoint
    bearing_deg: float
    distance_m: float

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


if __name__ == "__main__":
    from pathlib import Path
    sample_path = Path(__file__).parent.parent.parent / "data" / "sample.gpx"
    with open(sample_path, "rb") as f:
        points = parse_gpx(f.read())
    segments = split_into_segments(points)
    print(f" loaded {len(points)} Points")
    print(f"Start: {points[0]}")
    print(f"End:  {points[-1]}")
    print(f"{len(segments)} Segments")
    print(f"First Segment: {segments[0]}")