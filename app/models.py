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
        representative_point: A representative RoutePoint for the cluster (geographic midpoint of the middle segment).
    """
    segments: list[Segment]
    mean_bearing: float
    representative_point: RoutePoint

    @property
    def total_distance_m(self) -> float:
        """Total length of all segments in the cluster in meters."""
        return sum(s.distance_m for s in self.segments)


@dataclass
class ClusteredRoute:
    """A complete route represented as a list of SegmentClusters.

    Attributes:
        clusters: List of SegmentClusters that make up the route.
    """
    clusters: list[SegmentCluster]

    @property
    def total_distance_m(self) -> float:
        """Total length of all clusters in the route in meters."""
        return sum(c.total_distance_m for c in self.clusters)

    @property
    def representative_points(self) -> list[RoutePoint]:
        """List of representative RoutePoints, one per cluster."""
        return [c.representative_point for c in self.clusters]

@dataclass
class ClusterWeatherSnapshot:
    """Weather conditions observed at a specific cluster's representative point and time.

    Attributes:
        cluster: The SegmentCluster this snapshot belongs to.
        timestamp: UTC datetime when the rider is expected to reach this cluster.
        wind_speed_km_h: Average wind speed in km/h at 10 m height.
        wind_direction_deg: Meteorological wind origin direction in degrees (0–360, 0 = from north).
        wind_gusts_km_h: Wind gust speed in km/h.
        precipitation_mm_h: Precipitation accumulated over the 15-minute interval in mm
            (equivalent to mm/15 min; multiply by 4 to get mm/h).
    """
    cluster: SegmentCluster
    timestamp: datetime
    wind_speed_km_h: float
    wind_direction_deg: float
    wind_gusts_km_h: float
    precipitation_mm_h: float


