#! /usr/bin/env python
# -*- coding: utf-8 -*-
# V. Debaecker (TPZ-F) 2018
"""mgrs framing tool module"""
from dataclasses import dataclass
import logging
from math import ceil
import os

import numpy as np
import affine
from osgeo import gdal, osr
from shapely.wkt import loads
from shapely.geometry.base import BaseGeometry

from skimage.measure import block_reduce
from skimage.transform import SimilarityTransform
from skimage.transform import resize as skit_resize
from skimage.transform import warp as skit_warp

# internal packages
from core.image_file import S2L_ImageFile
from . import grids


log = logging.getLogger("Sen2Like")


@dataclass
class Box:
    """Simple Box class"""
    x_min: float
    y_min: float
    x_max: float
    y_max: float

@dataclass
class ReprojectResult:
    """Reprojection result class"""
    out_file_path: str
    """reprojected image file path"""
    dataset: gdal.Dataset
    """reprojected image as dataset"""


@dataclass
class MGRSGeoInfo:
    """MGRS tile geo info"""
    epsg: str
    """tile epsg"""
    geometry: BaseGeometry
    """tile geometry as UTM coords"""


# skimage / gdal resampling method mapping
order_to_gdal_resampling = {
    0: 'near',
    1: 'bilinear',
    3: 'cubic'
}


def resample(image: S2L_ImageFile, res: int, filepath_out: str) -> S2L_ImageFile:
    """Resample image to the given resolution

    Args:
        image (S2L_ImageFile): image to resample_
        res (int): new resolution
        filepath_out (str): resampled image destination file path

    Returns:
        S2L_ImageFile: resampled image as `S2L_ImageFile`
    """
    # create output dir if not exist
    output_dir = os.path.dirname(filepath_out)
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)

    # get input resolution
    input_res = image.xRes

    # SCIKIT resampling
    full_res = image.array

    # Method1: BLOCK REDUCE (10->30):
    if input_res == 10 and res % input_res == 0:
        R = int(res / input_res)  # resolution factor
        data = np.uint16(block_reduce(full_res, block_size=(R, R), func=np.mean) + 0.5)  # source: sen2cor

    # Method2: SCIKIT RESIZE (20->30, 60->30)
    else:
        size_up = full_res.shape[0] * input_res / res
        # order 3 is for cubic spline:
        data = (skit_resize(full_res.astype(np.uint16), ([size_up, size_up]), order=3) * 65535.).round().astype(
            np.uint16)

    return image.duplicate(filepath_out, array=data, res=res)


def pixel_center(image: S2L_ImageFile, tile_code: str):
    """Get mgrs tile center coordinates from tile code in image SRS

    Args:
        image (S2L_ImageFile): image to get srs from
        tile_code (str): MGRS tile code

    Returns:
        tuple: y/x coordinates
    """
    converter = grids.GridsConverter()
    utm, orientation, easting, northing = converter.get_mgrs_center(tile_code, utm=True)
    # UTM South vs. UTM North ?
    tile_srs = osr.SpatialReference()
    tile_srs.ImportFromEPSG(int('32' + ('6' if orientation == 'N' else '7') + str(utm)))
    image_srs = osr.SpatialReference(wkt=image.projection)
    if not tile_srs.IsSame(image_srs):
        transformation = osr.CoordinateTransformation(tile_srs, image_srs)
        northing, easting = transformation.TransformPoint((northing, easting))

    # northing = y = latitude, easting = x = longitude
    tr = affine.Affine(
        image.yRes, 0, image.yMax,
        0, image.xRes, image.xMin
    )
    y, x = (northing, easting) * (~ tr)
    return int(y), int(x)


def _reproject(filepath: str, dir_out: str, ds_src: gdal.Dataset, x_res: int, y_res: int, target_srs: osr.SpatialReference, order: int) -> ReprojectResult:
    """Reproject given dataset in the target srs in the given resolution

    Args:
        filepath (str): path of the file to reproject, mainly used to build output file path and log
        dir_out (str): output folder of the reproject file
        ds_src (gdal.Dataset): data set to reproject
        x_res (int): target x resolution
        y_res (int): target y resolution
        target_srs (osr.SpatialReference): target SRS
        order (int): resampling code, see `order_to_gdal_resampling` dict

    Raises:
        error: if reprojection fail

    Returns:
        ReprojectResult: reprojection result container
    """

    #
    splitted_filename = os.path.splitext(os.path.basename(filepath))
    reprojected_filepath = os.path.join(
        dir_out,
        f"{splitted_filename[0]}_REPROJ{splitted_filename[1]}"
    )

    log.info("Reproject %s to %s", filepath, reprojected_filepath)

    options = gdal.WarpOptions(
        dstSRS=target_srs,
        targetAlignedPixels=False, cropToCutline=False, xRes=x_res, yRes=y_res, dstNodata=0,
        resampleAlg=order_to_gdal_resampling.get(order),
        warpOptions=['NUM_THREADS=ALL_CPUS'], multithread=True)

    try:
        reproj_ds = gdal.Warp(
            reprojected_filepath,
            ds_src,
            options=options)

        return ReprojectResult(reprojected_filepath, reproj_ds)

    except RuntimeError as error:

        log.error("Cannot reproject %s", filepath)

        # close src dataset
        ds_src = None

        raise error

def get_mgrs_geo_info(tile_code: str) -> MGRSGeoInfo:
    """Get MGRS geo information of the given tile

    Args:
        tile_code (str): mgrs tile code

    Returns:
        MGRSGeoInfo: MGRS info
    """
    converter = grids.GridsConverter()
    roi = converter.getROIfromMGRS(tile_code)
    converter.close()
    log.debug(roi)

    return MGRSGeoInfo(roi['EPSG'][0], loads(roi['UTM_WKT'][0]))


def reframe(image: S2L_ImageFile, tile_code: str, filepath_out, dx=0., dy=0., order=3, dtype=None, margin=0, compute_offsets=False) -> S2L_ImageFile:
    """Reframe SINGLE band image in MGRS tile

    Args:
        image (S2L_ImageFile): image to reframe
        tile_code (str): MGRS tile code
        filepath_out (str): reframed image destination file path
        dx (float, optional): x correction to apply during reframing. Defaults to 0..
        dy (float, optional): y correction to apply during reframing. Defaults to 0..
        order (int, optional): type of resampling (see skimage warp). Defaults to 3.
        dtype (numpy dtype, optional): output image dtype name. Defaults to None (use input image dtype).
        margin (int, optional): margin to apply to output. Defaults to 0.
        compute_offsets (bool, optional): TODO : see with Vince. Defaults to False.

    Returns:
        S2L_ImageFile: reframed image
    """
    # get roi from mgrs tile_code
    mgrs_geo_info = get_mgrs_geo_info(tile_code)
    tile_geom = mgrs_geo_info.geometry

    box = Box(x_min=tile_geom.bounds[0] - margin * image.xRes, y_min=tile_geom.bounds[1] + margin * image.yRes,
              x_max=tile_geom.bounds[2] + margin * image.xRes, y_max=tile_geom.bounds[3] - margin * image.yRes)

    # UTM South vs. UTM North ?
    utm_offset = 0
    target_epsg = int(mgrs_geo_info.epsg)
    target_srs = osr.SpatialReference()
    target_srs.ImportFromEPSG(target_epsg)
    image_srs = osr.SpatialReference(wkt=image.projection)
    if not target_srs.IsSame(image_srs):
        if image_srs.GetUTMZone() == - target_srs.GetUTMZone():
            # UTM South vs. UTM North case
            utm_offset = 10000000
        else:
            image_epsg = image_srs.GetAuthorityCode(None)

            log.info("Image epsg and target epsg differ: %s vs %s.", image_epsg, target_epsg)

            ds_src = gdal.Open(image.filepath)
            geo = ds_src.GetGeoTransform()
            x_res = geo[1]
            y_res = geo[5]

            result = _reproject(
                image.filepath, 
                os.path.dirname(filepath_out), 
                ds_src, 
                x_res, y_res, target_srs, order
            )
            image = S2L_ImageFile(result.out_file_path)

    # compute offsets (grid origin + dx/dy
    if compute_offsets:
        r_dx = image.xRes * (((box.x_min - image.xMin) / image.xRes) % 1)
        r_dy = image.yRes * (((box.y_min - image.yMin) / image.yRes) % 1)
    else:
        r_dx = r_dy = 0

    # compute offsets (grid origin + dx/dy)
    xOff = (box.x_min - image.xMin + dx) / image.xRes
    yOff = (box.y_max - utm_offset - image.yMax - dy) / image.yRes

    # compute target size
    xSize = int(ceil((box.x_max - box.x_min) / image.xRes))
    ySize = int(ceil((box.y_max - box.y_min) / -image.yRes))

    # read image
    array = image.array
    # keep original dtype safe
    _dtype = None
    if dtype is None:
        _dtype = array.dtype
    else:
        _dtype = np.dtype(dtype)
        array = array.astype(_dtype)

    # Use NaN to avoid artefact when using skimage warp with bicubic
    if np.issubdtype(_dtype, np.floating):
        array[array == 0.0] = np.nan

    if xOff == 0 and yOff == 0 and image.xSize == xSize and image.ySize == ySize:
        new = array
    else:
        # translate and reframe (order= 0:nearest, 1: linear, 3:cubic)
        transform = SimilarityTransform(translation=(xOff, yOff))
        new = skit_warp(array, inverse_map=transform, output_shape=(ySize, xSize), order=order, preserve_range=True)

    # As we played with 0 and NaN, restore zeros for floating array
    # we have to restore zero for output NaN
    if np.issubdtype(_dtype, np.floating):
        new[np.isnan(new)] = 0.0

    # set into new S2L_ImageFile
    _origin=(box.x_min + r_dx, box.y_max + r_dy)
    return image.duplicate(filepath_out, array=new.astype(_dtype), origin=_origin, output_EPSG=target_epsg)


def reframe_multiband(filepath_in: str, tile_code: str, filepath_out: str, dx=0., dy=0., order=3):
    """Reframe multi band image in MGRS tile

    Args:
        filepath_in (str): input image file path
        tile_code (str): MGRS tile code
        filepath_out (str): destination file path of reframed image
        dx (float, optional): x correction to apply during reframing. Defaults to 0..
        dy (float, optional): y correction to apply during reframing. Defaults to 0..
        order (int, optional): type of resampling (see skimage warp). Defaults to 3.

    Returns:
        tuple: TODO : see with Vince
    """
    # get roi from mgrs tile_code
    mgrs_geo_info = get_mgrs_geo_info(tile_code)
    tile_geom = mgrs_geo_info.geometry

    box = Box(x_min=tile_geom.bounds[0], y_min=tile_geom.bounds[1],
              x_max=tile_geom.bounds[2], y_max=tile_geom.bounds[3])

    # open input
    ds_src = gdal.Open(filepath_in)
    geo = ds_src.GetGeoTransform()
    xRes = geo[1]
    yRes = geo[5]
    xMin = geo[0]
    yMax = geo[3]
    projection = ds_src.GetProjection()

    # UTM South vs. UTM North ?
    utm_offset = 0
    target_epsg = int(mgrs_geo_info.epsg)
    target_srs = osr.SpatialReference()
    target_srs.ImportFromEPSG(target_epsg)
    image_srs = osr.SpatialReference(wkt=projection)
    if not target_srs.IsSame(image_srs):
        if image_srs.GetUTMZone() == - target_srs.GetUTMZone():
            # UTM South vs. UTM North case
            utm_offset = 10000000
        else:
            image_epsg = image_srs.GetAuthorityCode(None)
            log.info("Image epsg and target epsg differ: %s vs %s.", image_epsg, target_epsg)
            result = _reproject(
                filepath_in, 
                os.path.dirname(filepath_in), 
                ds_src, 
                xRes, yRes, target_srs, order
            )
            ds_src = result.dataset

    # compute offsets
    xOff = (box.x_min - xMin + dx) / xRes
    yOff = (box.y_max - utm_offset - yMax - dy) / yRes

    xSize = int(ceil((box.x_max - box.x_min) / xRes))
    ySize = int(ceil((box.y_max - box.y_min) / -yRes))

    # write with gdal
    driver = gdal.GetDriverByName('GTiff')
    ds_dst = driver.Create(filepath_out, xsize=xSize, ysize=ySize,
                            bands=ds_src.RasterCount, eType=gdal.GDT_Int16)
    ds_dst.SetProjection(target_srs.ExportToWkt())
    geotranform = (box.x_min, xRes, 0, box.y_max, 0, yRes)
    log.debug(geotranform)
    ds_dst.SetGeoTransform(geotranform)

    # read image for each band
    for i in range(1, ds_src.RasterCount + 1):
        array = ds_src.GetRasterBand(i).ReadAsArray()

        # translate and reframe
        tf = SimilarityTransform(translation=(xOff, yOff))
        new = skit_warp(array, inverse_map=tf, output_shape=(ySize, xSize), order=order, preserve_range=True)

        # write band
        ds_dst.GetRasterBand(i).WriteArray(new)
    ds_dst.FlushCache()
    ds_src = None
    ds_dst = None

    return xOff, yOff
