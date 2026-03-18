from itertools import combinations

import geopandas as gpd
import leafmap.foliumap as leafmap
import matplotlib.pyplot as plt


def interactive_vector_field(gdf, layer_name="Vector Field", color="blue", zoom=6):
    if gdf.crs is None:
        gdf = gdf.set_crs("EPSG:4326")
    else:
        gdf = gdf.to_crs("EPSG:4326")

    center_lat = gdf.geometry.centroid.y.mean()
    center_lon = gdf.geometry.centroid.x.mean()
    m = leafmap.Map(center=[center_lat, center_lon], zoom=zoom)
    m.add_gdf(gdf, layer_name=layer_name, style={"color": color})
    return m


def plot_granule_pair(pairs_df, gdf, pair_index=0, show_overlap=True, ax=None):
    """
    Plot one overlapping pair of granules with a basic land background, zoomed to the granules.
    """
    if len(pairs_df) == 0:
        raise ValueError("No pairs found.")
    if pair_index >= len(pairs_df):
        raise IndexError(f"pair_index {pair_index} out of range. Max index: {len(pairs_df)-1}")

    pair = pairs_df.iloc[pair_index]
    g1 = gdf.loc[gdf['fileID'] == pair['granule1']].iloc[0]
    g2 = gdf.loc[gdf['fileID'] == pair['granule2']].iloc[0]

    if ax is None:
        fig, ax = plt.subplots(figsize=(8, 6))

    # Load Natural Earth land polygons
    world = gpd.read_file(gpd.datasets.get_path('naturalearth_lowres'))
    world.plot(ax=ax, color='lightgray', edgecolor='black', alpha=0.5)

    # Plot granules
    gpd.GeoSeries([g1.geometry]).plot(ax=ax, color='none', edgecolor='blue', linewidth=2, label="Granule 1")
    gpd.GeoSeries([g2.geometry]).plot(ax=ax, color='none', edgecolor='red', linewidth=2, label="Granule 2")

    # Optional overlap highlight
    if show_overlap:
        inter = g1.geometry.intersection(g2.geometry)
        if not inter.is_empty:
            gpd.GeoSeries([inter]).plot(ax=ax, color='purple', alpha=0.4, label='Overlap')

    # Zoom to granules' bounding box
    combined_bounds = g1.geometry.union(g2.geometry).bounds  # (minx, miny, maxx, maxy)
    ax.set_xlim(combined_bounds[0], combined_bounds[2])
    ax.set_ylim(combined_bounds[1], combined_bounds[3])

    ax.legend(loc='best')
    ax.set_title(f"Granule Pair {pair_index} (Overlap: {pair['overlap_ratio']:.2f}, Δt={pair['time_diff_days']}d)")
    ax.set_xlabel("Longitude")
    ax.set_ylabel("Latitude")
    ax.set_aspect('equal')
    plt.tight_layout()
    plt.show()


def interactive_granule_pair(pairs_df, gdf, pair_index=0):
    """
    Display an interactive map of one granule pair with Leafmap.
    Works for Polygon or MultiPolygon geometries and handles CRS.
    """
    if len(pairs_df) == 0:
        raise ValueError("No pairs found.")
    if pair_index >= len(pairs_df):
        raise IndexError(f"pair_index {pair_index} out of range.")

    # Ensure CRS
    if gdf.crs is None:
        gdf = gdf.set_crs("EPSG:4326")

    pair = pairs_df.iloc[pair_index]

    g1 = gdf[gdf['fileID'] == pair['granule1']]
    g2 = gdf[gdf['fileID'] == pair['granule2']]

    if g1.empty or g2.empty:
        raise ValueError("Granule(s) not found in GeoDataFrame for this pair_index")

    geom1 = g1.geometry.iloc[0]
    geom2 = g2.geometry.iloc[0]

    # Create map
    center_lat = gdf.geometry.centroid.y.mean()
    center_lon = gdf.geometry.centroid.x.mean()
    m = leafmap.Map(center=[center_lat, center_lon], zoom=4)

    # Add granules
    m.add_gdf(
        g1,
        layer_name='Granule 1',
        style={"color": "blue", "fillColor": "none", "weight": 2},
    )

    m.add_gdf(
        g2,
        layer_name='Granule 2',
        style={"color": "red", "fillColor": "none", "weight": 2},
    )

    # Add overlap
    overlap = geom1.intersection(geom2)
    if not overlap.is_empty:
        overlap_gdf = gpd.GeoDataFrame(geometry=[overlap], crs=gdf.crs)
        m.add_gdf(
        overlap_gdf,
        layer_name='Overlap',
        style={"color": "purple", "fillColor": "purple", "fillOpacity": 0.2},
    )

    # Zoom to granule bounds (flat list for Leafmap)
    combined = geom1.union(geom2)
    minx, miny, maxx, maxy = combined.bounds
    m.zoom_to_bounds([minx, miny, maxx, maxy])

    return m


def interactive_overlap_map(gdf):
    """
    Compute and display ONLY the overlapping polygons between granules.
    Each overlap is clickable and shows metadata.
    """
    if len(gdf) == 0:
        raise ValueError("GeoDataFrame is empty.")

    # Ensure CRS is WGS84 for Leaflet
    if gdf.crs is None:
        gdf = gdf.set_crs("EPSG:4326")
    else:
        gdf = gdf.to_crs("EPSG:4326")

    # Create map
    center_lat = gdf.geometry.centroid.y.mean()
    center_lon = gdf.geometry.centroid.x.mean()
    m = leafmap.Map(center=[center_lat, center_lon], zoom=4)

    # ---- Compute all overlaps ----
    overlap_records = []

    for (idx1, row1), (idx2, row2) in combinations(gdf.iterrows(), 2):

        inter = row1.geometry.intersection(row2.geometry)
        if not inter.is_empty:
            overlap_records.append({
                "pair": f"{row1.fileID} ∩ {row2.fileID}",
                "fileID1": row1.fileID,
                "fileID2": row2.fileID,
                "index1": idx1,
                "index2": idx2,
                "area": inter.area,
                "geometry": inter
            })

    if len(overlap_records) == 0:
        print("No overlaps found in the GeoDataFrame.")
        return m

    overlap_gdf = gpd.GeoDataFrame(overlap_records, crs=gdf.crs)

    # ---- Add clickable overlaps ----
    m.add_gdf(
        overlap_gdf,
        layer_name="Overlaps",
        info_mode="on_click",        # <- USE THIS INSTEAD OF popup=
        style={"color": "purple", "fillColor": "None", "fillOpacity": 0.7},
        columns=["pair", "fileID1", "fileID2", "index1", "index2", "area"],  # <- shown in popup
    )

    # Zoom to overlaps
    minx, miny, maxx, maxy = overlap_gdf.total_bounds
    m.zoom_to_bounds([minx, miny, maxx, maxy])

    return m
