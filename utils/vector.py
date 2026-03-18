import geopandas as gpd
import numpy as np
from shapely import affinity
from shapely.geometry import LineString, MultiLineString

from utils.buoy import interpolate_intersection, ckdnearest, calc_vectors


def create_arrow_gdf(x_arr, y_arr, dx_arr, dy_arr, crs_code, label, head_scale=0.25, head_angle=25):
    """
    Creates a GeoDataFrame of MultiLineStrings (Arrows).
    head_scale: 0.0 to 1.0 (Size of arrow head relative to vector length)
    head_angle: degrees (Angle of the arrow wings)
    """
    geometries = []

    for x, y, dx, dy in zip(x_arr, y_arr, dx_arr, dy_arr):
        # 1. Create the main shaft line
        start = (x, y)
        end = (x + dx, y + dy)
        shaft = LineString([start, end])

        # 2. Create the arrowheads using affine transformations
        # Scale the shaft down to create a "wing" length, anchored at the tip (end)
        # We assume the user wants the head at the 'end' point

        # Left Wing: Scale shaft -> Rotate positive degrees
        left_wing = affinity.scale(shaft, xfact=head_scale, yfact=head_scale, origin=end)
        left_wing = affinity.rotate(left_wing, head_angle, origin=end)

        # Right Wing: Scale shaft -> Rotate negative degrees
        right_wing = affinity.scale(shaft, xfact=head_scale, yfact=head_scale, origin=end)
        right_wing = affinity.rotate(right_wing, -head_angle, origin=end)

        # Combine into one geometry
        arrow_geom = MultiLineString([shaft, left_wing, right_wing])
        geometries.append(arrow_geom)

    # Repeat label to match length
    data = {'label': [label] * len(geometries)}

    gdf = gpd.GeoDataFrame(data, geometry=geometries, crs=f"epsg:{crs_code}")
    return gdf.to_crs("epsg:4326")


def get_vector_properties(vector):
    """Calculates magnitude and direction (angle) of a vector [dx, dy]"""
    dx, dy = vector[0], vector[1]
    magnitude = np.sqrt(dx**2 + dy**2)
    # Use arctan2 for correct quadrant, returns angle in radians
    # np.arctan2(y, x)
    direction_rad = np.arctan2(dy, dx)
    # Convert to degrees and normalize to [0, 360) for easier comparison
    direction_deg = np.degrees(direction_rad)
    direction_deg = direction_deg % 360  # 0 to 360 degrees
    return magnitude, direction_deg


def calc_direction_magnitude_error(buoy_vector, ice_vector):
    """
    Calculate the error in magnitude and direction between buoy and ice vectors.
    """
    buoy_mag, buoy_dir = get_vector_properties(buoy_vector)
    ice_mag, ice_dir = get_vector_properties(ice_vector)

    # 1. Magnitude Error (Simple absolute difference)
    mag_error = abs(buoy_mag - ice_mag)

    # 2. Direction Error (Smallest angular difference, accounting for 360-degree wrap)
    # The difference can range from -360 to 360.
    dir_diff = buoy_dir - ice_dir
    # Normalize to [-180, 180] range for smallest angle
    if dir_diff > 180:
        dir_error = abs(dir_diff - 360)
    elif dir_diff < -180:
        dir_error = abs(dir_diff + 360)
    else:
        dir_error = abs(dir_diff)

    return mag_error, dir_error, buoy_mag, buoy_dir, ice_mag, ice_dir


def compare_buoy_ice_direction_magnitude(intersection, ice_gdf_proj, start_datetime, end_datetime):
    """
    Calcuate the magnitude and direction errors between a buoy and RGPS sea ice vectors.

    :param intersection: Gdf of time-matched buoy points
    :param ice_gdf_proj: Gdf of the RGPS sea ice vector field
    :return: (mag_error, dir_error, buoy_mag, buoy_dir, ice_mag, ice_dir, ...)
    """
    interpolated_buoy_xy = interpolate_intersection(intersection, start_datetime, end_datetime)

    # Find the nearest ice vector to the buoy's starting position
    _, nn_idx = ckdnearest(interpolated_buoy_xy[0], ice_gdf_proj)

    # The ice vector's coordinates are stored in the 'points' column of the nearest row
    ice_xy = ice_gdf_proj.iloc[nn_idx].points

    # Calculate the actual buoy vector and the matched ice vector
    buoy_vector, ice_vector = calc_vectors(interpolated_buoy_xy, ice_xy)

    # Calculate the errors
    mag_error, dir_error, buoy_mag, buoy_dir, ice_mag, ice_dir = calc_direction_magnitude_error(buoy_vector, ice_vector)

    # Return results, including original vector components for logging/debugging
    return mag_error, dir_error, buoy_mag, buoy_dir, ice_mag, ice_dir, buoy_vector, ice_vector
