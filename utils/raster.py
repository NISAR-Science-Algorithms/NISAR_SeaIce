import os

import numpy as np
import rasterio
from osgeo import gdal, osr


clip_values = {
    'VVVV': {'min': -27, 'max': -6},
    'HHHH': {'min': -30, 'max': -5},
}


def nisar_to_geotiff(h5_file, output_dir, frequency='frequencyB', polarization='VVVV', convert_db=True, clip=True):
    """Export a NISAR GCOV HDF5 image to a GeoTIFF.

    Args:
        h5_file: path to NISAR .h5 file
        output_dir: directory for output GeoTIFF
        frequency: HDF5 frequency group (e.g. 'frequencyB')
        polarization: polarization key (e.g. 'VVVV', 'HHHH')
        convert_db: convert power to dB (10*log10)
        clip: clip dB values to preset range (only used when convert_db=True)
    """
    import h5py

    with h5py.File(h5_file, 'r') as f:
        grid = f['science']['LSAR']['GCOV']['grids'][frequency]
        ds_x = grid['xCoordinates'][()]
        ds_y = grid['yCoordinates'][()]
        ds_epsg = grid['projection'][()]
        data = grid[polarization][()]
        rtc = grid['rtcGammaToSigmaFactor'][()]

    sigma0 = data * rtc

    sigma0[sigma0 <= 0] = np.nan  # zero/negative values produce -inf in log; mask them

    if convert_db:
        sigma0 = 10 * np.log10(sigma0)
        if clip:
            lo, hi = clip_values[polarization]['min'], clip_values[polarization]['max']
            np.clip(sigma0, lo, hi, out=sigma0)

    nodata = 0.0
    sigma0 = np.where(np.isnan(sigma0), nodata, sigma0)

    pixel_width = ds_x[1] - ds_x[0]
    origin_x = ds_x[0]
    if ds_y[1] < ds_y[0]:  # descending Y — standard GeoTIFF orientation
        pixel_height = ds_y[1] - ds_y[0]
        origin_y = ds_y[0]
    else:                   # ascending Y — flip data so origin is top-left
        pixel_height = -(ds_y[1] - ds_y[0])
        origin_y = ds_y[-1]
        sigma0 = np.flipud(sigma0)

    geotransform = (origin_x, pixel_width, 0.0, origin_y, 0.0, pixel_height)

    suffix = f'_{frequency}_{polarization}.tif'
    out_path = os.path.join(output_dir, os.path.basename(h5_file).replace('.h5', suffix))

    driver = gdal.GetDriverByName('GTiff')
    out_ds = driver.Create(out_path, sigma0.shape[1], sigma0.shape[0], 1, gdal.GDT_Float32)
    out_ds.SetGeoTransform(geotransform)
    srs = osr.SpatialReference()
    srs.ImportFromEPSG(int(ds_epsg))
    out_ds.SetProjection(srs.ExportToWkt())
    band = out_ds.GetRasterBand(1)
    band.SetNoDataValue(nodata)
    band.WriteArray(sigma0)
    band.FlushCache()
    out_ds = None

    print(f'Saved: {out_path}')
    return out_path


def load_data(fpath, band=1):
    with rasterio.open(fpath) as src:
        data_array = src.read(band)
        transform = src.transform
    return data_array, transform


def get_geocorner(arr, geo_tran):
    length, width = arr.shape
    ulx, uly = geo_tran[2], geo_tran[5]
    xres, yres = geo_tran[0], geo_tran[4]
    lrx = ulx + (width * xres)
    lry = uly + (length * yres)
    # Raster geo corners
    geocor = (ulx, lrx, lry, uly)

    return geocor


def combine_geocor(geocor1, geocor2):
    combined_corners = (
    min(geocor1[0], geocor2[0]),  # min of ulx
    max(geocor1[1], geocor2[1]),  # max of lrx
    min(geocor1[2], geocor2[2]),  # min of lry
    max(geocor1[3], geocor2[3])   # max of ul
    )

    return combined_corners
