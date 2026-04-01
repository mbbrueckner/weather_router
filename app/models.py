"""Data models for GPS route points, segments, and segment clusters.

This module defines the core data structures used to represent GPS route points, segments between points, and clusters of segments with similar bearings. These models are used throughout the application for processing GPX files, clustering route segments, and associating weather data with specific locations along a route.
"""

__author__ = "mbbrueckner"
__version__ = "1.0.0"

from dataclasses import dataclass
from datetime import datetime

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


@dataclass
class SegmentCluster:
    """A Cluster of consecutive Segments with similar bearing, representing a straight portion of the route.

    Attributes:
        segments: List of Segments in the cluster.
        mean_bearing: Average bearing of the segments in degrees (0–360).
        total_distance_km: Total distance of the cluster in kilometers.
        representative_lat: Latitude of a representative point for the cluster (e.g., start of first segment).
        arrival_time: Timestamp of arrival at the representative point, if available.
    """
    segments: list[Segment]       
    mean_bearing: float           
    total_distance_m: float      
    representative_point:RoutePoint        

