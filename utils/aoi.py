import os
import xml.etree.ElementTree as ET
from shapely import wkt
from shapely.geometry import Polygon
from shapely.validation import explain_validity


def check_polygon_validity(polygon_wkt):
    """
    Check if a polygon (in WKT format) is valid.
    If not valid, print the reason for invalidity.
    """
    polygon = wkt.loads(polygon_wkt)
    if not polygon.is_valid:
        reason = explain_validity(polygon)
        print(f"Invalid polygon: {reason}")
    else:
        print("Polygon is valid.")


def kml_to_wkt(kml_path):
    """
    Extracts all <Polygon> coordinate sets from a KML file
    and returns their geometries in WKT format.
    """
    tree = ET.parse(kml_path)
    root = tree.getroot()

    # Handle namespaces dynamically (KML files often have one)
    ns = {'kml': root.tag.split('}')[0].strip('{')} if '}' in root.tag else {}

    wkt_list = []

    for coords_tag in root.findall('.//kml:Polygon//kml:coordinates', ns):
        coords_text = coords_tag.text.strip()
        coords = []
        for c in coords_text.split():
            lon, lat, *_ = map(float, c.split(','))
            coords.append((lon, lat))
        poly = Polygon(coords)
        wkt_list.append(poly.wkt)

    return wkt_list


def load_aoi_polygon(aoi_polygon):
    """
    Accepts either a WKT polygon string or a file path to a .kml file.
    If given a .kml file, converts it to WKT using kml_to_wkt().

    Returns:
        WKT polygon string.
    """
    # CASE 1 — Check if it's valid WKT (POLYGON, MULTIPOLYGON, etc.)
    try:
        geom = wkt.loads(aoi_polygon)
        # If this succeeds, it *is* WKT, so return as-is
        return aoi_polygon
    except Exception:
        pass  # Not WKT, continue to file-path logic

    # CASE 2 — Must be a file path
    if not isinstance(aoi_polygon, str):
        raise TypeError("aoi_polygon must be either a WKT string or a file path string.")

    if not os.path.exists(aoi_polygon):
        raise FileNotFoundError(f"File path does not exist: {aoi_polygon}")

    # Check extension
    if not aoi_polygon.lower().endswith(".kml"):
        raise ValueError("If 'aoi_polygon' is a file path, it must end with '.kml'")

    # Convert using your existing function
    wkt_list = kml_to_wkt(aoi_polygon)
    if not wkt_list:
        raise ValueError("kml_to_wkt() returned an empty list.")

    return wkt_list[0]


def polygon_hemisphere(wkt_polygon, return_both=False):
    """
    Determine the hemisphere(s) where a polygon is located.

    Parameters
    ----------
    wkt_polygon : str
        WKT string of the polygon.
    return_both : bool
        If True, return both latitudinal and longitudinal hemispheres.

    Returns
    -------
    str or tuple
        Hemisphere classification.
    """
    geom = wkt.loads(wkt_polygon)
    centroid = geom.centroid
    lat = centroid.y
    lon = centroid.x

    lat_hemi = "North" if lat >= 0 else "South"
    lon_hemi = "East" if lon >= 0 else "West"

    if lat_hemi == "North":
        epsg_code = 3413  # NSIDC Sea Ice Polar Stereographic North
    else:
        epsg_code = 3031  # NSIDC Sea Ice Polar Stereographic South

    if return_both:
        print(f"Polygon hemispheres Latitude: {lat_hemi}, Longitude: {lon_hemi}")
        return lat_hemi, lon_hemi, epsg_code
    else:
        print(f"Polygon hemisphere Latitude: {lat_hemi}")
        return lat_hemi, epsg_code  # default: just north/south
