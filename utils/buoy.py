import numpy as np
import pandas as pd
import geopandas as gpd
from scipy.spatial import cKDTree
from shapely.geometry import Point


def make_convex_hull(ice_gdf):
    """
    This function creates a geometry of the convex hull of the sea ice movement vector field

    :param ice_gdf_proj: Gdf of the RGPS sea ice movement vector field in the to_epsg projection
    :return: Gdf containing the convex hull geometry of the sea ice field in the to_epsg projection
    """
    # Convert LineStrings into list of two points (start and end points)
    ice_gdf['points'] = ice_gdf.apply(lambda x: [y for y in x['geometry'].coords], axis=1)

    # create convex hull
    convex_hull = gpd.GeoSeries(
        [
            Point(tup) for tup_list in ice_gdf['points'].to_list() for tup in tup_list
        ]
    ).unary_union.convex_hull

    # convert Shapely convex hull to gpd gdf
    ch_gdf = gpd.GeoDataFrame(geometry=gpd.GeoSeries(convex_hull))

    return ch_gdf


def get_nearest_times(target_datetime, gdf):
    """
    Get the two lines with the closest datetimes above and below the target datetime.
    """
    # FIX: Sort by datetime column to ensure chronological order
    gdf = gdf.sort_values('datetime')

    exactmatch = gdf[gdf.datetime == target_datetime]
    if not exactmatch.empty:
        return exactmatch
    else:
        # Filter for rows before and after the target
        lower_candidates = gdf[gdf.datetime < target_datetime]
        upper_candidates = gdf[gdf.datetime > target_datetime]

        # Check if we have data on both sides
        if lower_candidates.empty or upper_candidates.empty:
            return gpd.GeoDataFrame()

        # FIX: Select the last row of the past (closest to target)
        # and the first row of the future (closest to target)
        # using iloc (position) rather than loc (label)
        lower_neighbor = lower_candidates.iloc[-1:]
        upper_neighbor = upper_candidates.iloc[:1]

        return pd.concat([lower_neighbor, upper_neighbor])


def load_and_merge_daily_buoy_gdfs(handler, target_date):
    """
    Load buoy points gdfs from the file system for the target_date and days
    around target_date as necessary

    :param target_date: date of interest
    :return: gdf of buoys for the days around target_date
    """
    buoy_gdf = handler.get_GDF_from_database_with_date(target_date)

    return buoy_gdf


def gdf_spatial_intersection(buoy_gdf, ice_gdf):
    """
    Finds any buoys that are in the same area as the convex hull of the sea ice vectors

    :param buoy_gdf: Gdf of buoys in the to_epsg projection
    :param ice_gdf: Gdf of the RGPS sea ice movement vector field in the to_epsg projection
    :return: Gdf containing all buoys that are in the RGPS vector field. Filter by time next.
    """
    buoy_gdf['datetime'] = buoy_gdf.index
    ch_gdf = make_convex_hull(ice_gdf)
    intersection = gpd.overlay(buoy_gdf, ch_gdf, how='intersection')

    return intersection


def find_buoy_matches(handler, target_datetime, ice_gdf):
    """
    Find the nearest upper and lower time bounded buoy data points within the sea ice area

    :param target_datetime: Datetime of the RGPS sea ice image
    :param ice_gdf: Gdf of the RGPS sea ice movement vector field in the to_epsg projection
    :return: gdf containing the buoy data points that are within the ice_gdf area and were captured immediately before and after target_datetime
    """
    # start date - load daily buoy gdf according to parsed dates
    buoy_gdf = load_and_merge_daily_buoy_gdfs(handler, target_datetime)
    buoy_gdf = buoy_gdf.set_geometry('geometry')

    # Ensure the index is a DatetimeIndex and convert it to a column
    if isinstance(buoy_gdf.index, pd.DatetimeIndex):
        if buoy_gdf.index.tz is None:
            buoy_gdf = buoy_gdf.tz_localize('UTC')
    else:
        raise ValueError("Expected DatetimeIndex")

    # Create a datetime column from the index
    buoy_gdf = buoy_gdf.copy()
    buoy_gdf["datetime"] = buoy_gdf.index

    # find ice_gdf projection and use it throughout analysis
    ice_gdf_epsg = ice_gdf.crs.to_epsg()

    # project to ice_gdf epsg to be able to do the intersection
    buoy_gdf_proj = buoy_gdf.to_crs(ice_gdf_epsg)

    # get intersection
    intersection = gdf_spatial_intersection(buoy_gdf_proj, ice_gdf)

    buoy_ids = list(set(intersection['BuoyID']))
    if not buoy_ids:
        return gpd.GeoDataFrame()
    time_intersection = gpd.GeoDataFrame()
    for buoy in buoy_ids:
        gdf_per_buoy = intersection[intersection['BuoyID'] == buoy]
        time_intersection_per_buoy = get_nearest_times(target_datetime, gdf_per_buoy)
        time_intersection = pd.concat([time_intersection, time_intersection_per_buoy])

    return time_intersection


def interpolate_intersection(intersection, start_datetime, end_datetime):
    """
    geometry for linear interpolation between two buoy positions

    :param intersection: geodataframe containing intersection of buoy and sea ice
    :param start_datetime: start datetime of datetime object for sea ice gdf
    :param end_datetime: end datetime of datetime object for sea ice gdf
    :return: start and end interpolated positions
    """

    def interpolate_buoy(zb1, zb2, tb1, tb2, ti0):
        """
        linear interpolation between two buoy positions

        :param zb2: buoy 2 position
        :param tb1: buoy 1 time
        :param tb2: buoy 2 time
        :param ti0: target time
        :return: buoy position at target time
        """
        dt = tb2 - tb1  # time difference
        vb = (np.array(zb2) - np.array(zb1)) / dt.total_seconds()
        tf = (ti0 - tb1).total_seconds()
        zb0 = zb1 + vb * tf  # estimate the buoy's position at ti0 via linear interpolation
        return zb0

    row_start0 = intersection.iloc[0]
    row_start1 = intersection.iloc[1]
    row_end0 = intersection.iloc[-1]
    row_end1 = intersection.iloc[-2]

    row_start0xy = row_start0.geometry.coords[0]
    row_start1xy = row_start1.geometry.coords[0]
    row_end0xy = row_end0.geometry.coords[0]
    row_end1xy = row_end1.geometry.coords[0]

    row_start0t = row_start0.datetime
    row_start1t = row_start1.datetime
    row_end0t = row_end0.datetime
    row_end1t = row_end1.datetime

    start_int_xy = interpolate_buoy(row_start0xy, row_start1xy, row_start0t, row_start1t, start_datetime)
    end_int_xy = interpolate_buoy(row_end1xy, row_end0xy, row_end1t, row_end0t, end_datetime)

    return start_int_xy, end_int_xy


def ckdnearest(point, gdf):
    """
    :param point: interpolated buoy point
    :param gdf: sea ice gdf
    :return: the nearest point in the gdf to the buoy point
    """
    # FIX: Extract ONLY the start coordinate (index 0) of every geometry
    # We want to match where the ice flow ORIGINATED, not where it ended.
    B = [np.array(geom.coords[0]) for geom in gdf.geometry.to_list()]

    ckd_tree = cKDTree(B)
    dist, idx = ckd_tree.query(point, k=1)

    # FIX: No need to divide by 2 anymore.
    # Since B now has exactly one point per row in the GDF, idx maps 1-to-1.
    nn_idx = idx

    return dist, nn_idx


def calc_vectors(interpolated_buoy_xy, ice_xy):
    """
    This function finds the vector [x,y] of the interpolated (virtual) buoy movement and sea ice movement

    :param interpolated_buoy_xy: interpolated buoy movement points
    :param ice_xy: ice vector points
    :return: ice vector and buoy vector
    """

    def make_vector(points):
        x_disp = points[1][0] - points[0][0]
        y_disp = points[1][1] - points[0][1]
        return [x_disp, y_disp]

    return make_vector(interpolated_buoy_xy), make_vector(ice_xy)


def calc_buoy_rmse(interp_buoy, est_buoy, start_datetime, end_datetime):
    import math
    """
    Calculate RMSE for a given vector
    """
    x1, y1 = interp_buoy[1][0], interp_buoy[1][1]
    x2, y2 = est_buoy[0], est_buoy[1]

    # Calculate Error as Distance (Euclidean)
    delta_x = x1 - x2
    delta_y = y1 - y2
    dist_error = np.sqrt(delta_x**2 + delta_y**2)
    # Time normalization
    time_difference = end_datetime - start_datetime
    time_hours = time_difference.total_seconds() / 3600
    # Calculate Drift Rate (Error per day)
    # If the buoy is off by 'dist_error' over 'time_hours',
    # how far off would it be in 24 hours?
    daily_drift_rate = (dist_error / time_hours) * 24  # daily_drift_rate
    # Component-wise drift
    # if the error is biased toward East/West or North/South
    normal_rms_x = (delta_x / time_hours) * 24
    normal_rms_y = (delta_y / time_hours) * 24

    return dist_error, delta_x, delta_y, daily_drift_rate, normal_rms_x, normal_rms_y, interp_buoy[0][0], interp_buoy[0][1], interp_buoy[1][0], interp_buoy[1][1]


def compare_buoy_ice(intersection, ice_gdf_proj, start_datetime, end_datetime):
    """
    Calcuate the RMSE values from a buoy and RGPS sea ice vectors

    :param intersection: Gdf containing all buoys points nearest to the start and end datetimes and within the sea ice vector field in the to_epsg projection
    :param ice_gdf_proj: Gdf of the RGPS sea ice movement vector field in the to_epsg projection
    :param start_datetime: datetime of the first RGPS ice image
    :param end_datetime: datetime of the second RGPS ice image
    :return: (rms, rms_x, rms_y, normal_rms_x, normal_rms_y)
    """
    interpolated_buoy_xy = interpolate_intersection(intersection, start_datetime, end_datetime)
    dist, nn_idx = ckdnearest(interpolated_buoy_xy[0], ice_gdf_proj)
    ice_xy = ice_gdf_proj.iloc[nn_idx].points
    buoy_vector, ice_vector = calc_vectors(interpolated_buoy_xy, ice_xy)
    est_buoy = interpolated_buoy_xy[0] + ice_vector  # estimate buoy position at end time using ice vector
    # get rmse
    dist_error, x_error, y_error, error_per_day, x_error_per_day, y_error_per_day, x1, y1, x2, y2 = calc_buoy_rmse(interpolated_buoy_xy,
                                                                                                                   est_buoy,
                                                                                                                   start_datetime,
                                                                                                                   end_datetime)

    return dist_error, x_error, y_error, error_per_day, x_error_per_day, y_error_per_day, x1, y1, x2, y2, est_buoy, ice_vector, nn_idx, dist
