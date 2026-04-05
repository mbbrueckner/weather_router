""" Route analysis by weather conditions.

This module orchestrates the analysis of a GPX file, extracting route points and clustering them based on weather conditions.
"""

__author__ = "mbbrueckner"
__version__ = "1.0.0"

import datetime

from app.services.gpx_parser import get_clustered_route
from app.services.weather import get_weather_for_route
from app.services.route_scorer import score_segment


def analyze_route(gpx_file : bytes, avg_speed_kmh: float, start_time: datetime) -> float:
    """Analyze a GPX route and return an overall score based on weather conditions.

    Args:
        gpx_file: The GPX file content as bytes.
        avg_speed_kmh: The average speed in km/h to use for clustering.
        start_time: The start time for weather data retrieval.
    Returns:
        A float score where higher values indicate more favorable weather conditions along the route.
    """
    
    route_clusters = get_clustered_route(gpx_file, avg_speed_kmh, start_time)
    weather_snapshots = get_weather_for_route(route_clusters)
    
    total_score = 0.0
    for snapshot in weather_snapshots:
        score = score_segment(snapshot)
        total_score += score * snapshot.cluster.total_distance_m

    return total_score / route_clusters.total_distance_m
    

    

    

