from itertools import combinations

import geopandas as gpd
import pandas as pd
from shapely.geometry import Point


def find_overlapping_pairs(gdf, overlap_threshold=0.3, max_days=3):
    """
    Identify pairs of Sentinel-1 granules that overlap spatially and are close in time.

    Parameters
    ----------
    gdf : geopandas.GeoDataFrame
        Must contain columns:
        - 'geometry' (Polygon)
        - 'startTime' (ISO datetime string)
        - 'stopTime' (ISO datetime string)
    overlap_threshold : float, optional
        Minimum fractional area overlap (default 0.3)
    max_days : int, optional
        Maximum allowed time gap between acquisitions in days (default 3)

    Returns
    -------
    pandas.DataFrame
        A DataFrame of valid granule pairs with overlap and time difference.
    """
    # Ensure datetime type
    gdf = gdf.copy()
    gdf['startTime'] = pd.to_datetime(gdf['startTime'])
    gdf['stopTime'] = pd.to_datetime(gdf['stopTime'])

    # Sort by start time
    gdf = gdf.sort_values('startTime').reset_index(drop=True)

    pairs = []
    n = len(gdf)

    for i in range(n):
        for j in range(i + 1, n):
            g1, g2 = gdf.iloc[i], gdf.iloc[j]

            # Compute temporal difference
            time_diff = abs((g2['startTime'] - g1['stopTime']).days)
            if time_diff > max_days:
                # Because gdf is sorted, all later granules will be even farther in time
                break

            # Compute intersection over smaller area
            inter = g1.geometry.intersection(g2.geometry)
            if inter.is_empty:
                continue

            overlap_ratio = inter.area / min(g1.geometry.area, g2.geometry.area)

            if overlap_ratio >= overlap_threshold:
                pairs.append({
                    'granule1': g1['fileID'],
                    'granule2': g2['fileID'],
                    'startTime1': g1['startTime'],
                    'startTime2': g2['startTime'],
                    'time_diff_days': time_diff,
                    'overlap_ratio': overlap_ratio
                })

    return pd.DataFrame(pairs)


def select_scenes_overlapping_a_station(gdf, lon, lat):
    """
    Returns a subset of the original GeoDataFrame containing only the scenes
    whose overlap contains the provided coordinate (lon, lat).
    Keeps ALL original columns and CRS.
    """
    if gdf.empty:
        raise ValueError("Input GeoDataFrame is empty.")

    # If CRS missing, assume polygons already in lon/lat
    if gdf.crs is None:
        gdf = gdf.set_crs("EPSG:4326")
    else:
        gdf = gdf.to_crs("EPSG:4326")

    point = Point(lon, lat)

    # select all scenes that contain the point
    scenes_containing_point = gdf[gdf.geometry.contains(point)]

    if len(scenes_containing_point) < 2:
        # Not enough scenes to form an overlap
        return gdf.iloc[0:0]

    # find which of these scenes actually overlap each other at the point
    overlapping_idx = set()

    for (idx1, row1), (idx2, row2) in combinations(scenes_containing_point.iterrows(), 2):

        inter = row1.geometry.intersection(row2.geometry)
        if not inter.is_empty and inter.contains(point):
            overlapping_idx.add(idx1)
            overlapping_idx.add(idx2)

    # No overlapping scenes at this point
    if not overlapping_idx:
        return gdf.iloc[0:0]

    # return the filtered scenes
    return gdf.loc[sorted(overlapping_idx)]
