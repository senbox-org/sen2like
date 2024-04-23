#! /usr/bin/env python
# -*- coding: utf-8 -*-
# Copyright (c) 2023 ESA.
#
# This file is part of sen2like.
# See https://github.com/senbox-org/sen2like for further info.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""mgrs framing tool module"""
import logging
import os
from dataclasses import dataclass
from math import ceil
from typing import NamedTuple

import numpy as np
import pandas as pd
from numpy.typing import NDArray
from osgeo import gdal, osr
from shapely.geometry.base import BaseGeometry
from shapely.wkt import loads
from skimage.measure import block_reduce
from skimage.transform import SimilarityTransform, estimate_transform
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


class _CorrectionConfig(NamedTuple):
    """Array correction config.
    method allowed : translation | polynomial
    For a translation method, x_off, y_off, x_size and y_size MUST be setted
    For a polynomial method, klt_dir must be set
    """
    method: str
    x_off: float
    y_off: float
    x_size: int
    y_size: int
    klt_dir: str


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


def _do_correction(array: NDArray, order: int, config: _CorrectionConfig):
    """Apply correction to array

    Args:
        array (NDArray): array to transform
        order (int): type of resampling
        config (CorrectionConfig): correction config

    Raises:
        ValueError: if correction method is unknown

    Returns:
        NDArray: corrected array
    """
    if config.method == "translation":
        log.info("Translation correction")
        # translate and reframe (order= 0:nearest, 1: linear, 3:cubic)
        transform = SimilarityTransform(translation=(config.x_off, config.y_off))
        return skit_warp(
            array,
            inverse_map=transform,
            output_shape=(config.y_size, config.x_size),
            order=order,
            preserve_range=True
        )

    if config.method == "polynomial":
        log.info("Polynomial correction")
        # klt_dir should be working dir
        data_frame = pd.read_csv(os.path.join(config.klt_dir, "KLT.csv"), sep=";")

        dst = np.array(
            [
                (data_frame.x0 + data_frame.dx).to_numpy(),
                (data_frame.y0 + data_frame.dy).to_numpy()
            ]
        ).T

        src = np.array([data_frame.x0.to_numpy(), data_frame.y0.to_numpy()]).T
        transform = estimate_transform(config.method, src, dst)
        return skit_warp(array, inverse_map=transform, preserve_range=True, cval=1000)

    raise ValueError(f"Unknown correction method: {config.method}")


def reframe(
    image: S2L_ImageFile,
    tile_code: str,
    filepath_out,
    dx=0.,
    dy=0.,
    order=3,
    dtype=None,
    method="translation"
) -> S2L_ImageFile:
    """Reframe SINGLE band image in MGRS tile

    Args:
        image (S2L_ImageFile): image to reframe
        tile_code (str): MGRS tile code
        filepath_out (str): reframed image destination file path, should be working dir
        dx (float, optional): x correction to apply during reframing. Defaults to 0..
        dy (float, optional): y correction to apply during reframing. Defaults to 0..
        order (int, optional): type of resampling (see skimage warp). Defaults to 3.
        dtype (numpy dtype, optional): output image dtype name. Defaults to None (use input image dtype).
        method (str, optional): geometry correction strategy to apply. 
            Expect 'polynomial' or 'translation". Defaults to 'translation'.
            If polynomial, KLT.csv file should be located in dirname of filepath_out

    Returns:
        S2L_ImageFile: reframed image
    """
    # get roi from mgrs tile_code
    mgrs_geo_info = get_mgrs_geo_info(tile_code)
    tile_geom = mgrs_geo_info.geometry

    box = Box(x_min=tile_geom.bounds[0], y_min=tile_geom.bounds[1],
              x_max=tile_geom.bounds[2], y_max=tile_geom.bounds[3])

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
        new_array = array
    else:
        correction_config = _CorrectionConfig(
            method,
            xOff,
            yOff,
            xSize,
            ySize,
            os.path.dirname(filepath_out)
        )
        new_array = _do_correction(array, order, correction_config)

    # As we played with 0 and NaN, restore zeros for floating array
    # we have to restore zero for output NaN
    if np.issubdtype(_dtype, np.floating):
        new_array[np.isnan(new_array)] = 0.0

    # set into new S2L_ImageFile
    _origin=(box.x_min, box.y_max)
    return image.duplicate(filepath_out, array=new_array.astype(_dtype), origin=_origin, output_EPSG=target_epsg)


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
