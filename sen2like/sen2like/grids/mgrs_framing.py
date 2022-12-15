#! /usr/bin/env python
# -*- coding: utf-8 -*-
# V. Debaecker (TPZ-F) 2018

import logging
import os
from collections import namedtuple
from math import ceil

import numpy as np
import affine
from osgeo import gdal, osr
from shapely.wkt import loads
from skimage.measure import block_reduce
from skimage.transform import SimilarityTransform
from skimage.transform import resize as skit_resize
from skimage.transform import warp as skit_warp

# internal packages
from . import grids

log = logging.getLogger("Sen2Like")


def resample(imagein, res, filepath_out):
    # create output dir if not exist
    dirout = os.path.dirname(filepath_out)
    if not os.path.exists(dirout):
        os.makedirs(dirout)

    # get input resolutionresolution
    input_res = imagein.xRes

    # SCIKIT resampling
    fullRes = imagein.array

    # Method1: BLOCK REDUCE (10->30):
    if input_res == 10 and res % input_res == 0:
        R = int(res / input_res)  # resolution factor
        data = np.uint16(block_reduce(fullRes, block_size=(R, R), func=np.mean) + 0.5)  # source: sen2cor

    # Method2: SCIKIT RESIZE (20->30, 60->30)
    else:
        sizeUp = fullRes.shape[0] * input_res / res
        # order 3 is for cubic spline:
        data = (skit_resize(fullRes.astype(np.uint16), ([sizeUp, sizeUp]), order=3) * 65535.).round().astype(
            np.uint16)

    imageout = imagein.duplicate(filepath_out, array=data, res=res)

    return imageout


def pixel_center(image, tilecode):
    # get center from mgrs tilecode
    converter = grids.GridsConverter()
    utm, orientation, easting, northing = converter.get_mgrs_center(tilecode, utm=True)
    # UTM South vs. UTM North ?
    inSR = osr.SpatialReference()
    inSR.ImportFromEPSG(int('32' + ('6' if orientation == 'N' else '7') + str(utm)))
    outSR = osr.SpatialReference(wkt=image.projection)
    if not inSR.IsSame(outSR):
        transformater = osr.CoordinateTransformation(inSR, outSR)
        northing, easting = transformater.TransformPoint((northing, easting))

    # northin = y = latitude, easting = x = longitude
    tr = affine.Affine(
        image.yRes, 0, image.yMax,
        0, image.xRes, image.xMin
    )
    y, x = (northing, easting) * (~ tr)
    return int(y), int(x)


def reframe(image, tilecode, filepath_out, dx=0., dy=0., order=3, dtype=None, margin=0, compute_offsets=False):
    # get roi from mgrs tilecode
    converter = grids.GridsConverter()
    roi = converter.getROIfromMGRS(tilecode)
    converter.close()
    log.debug(roi)

    # load wkt
    g = loads(roi['UTM_WKT'][0])
    Box = namedtuple('Box', ['xMin', 'yMin', 'xMax', 'yMax'])
    box = Box(xMin=g.bounds[0] - margin * image.xRes, yMin=g.bounds[1] + margin * image.yRes,
              xMax=g.bounds[2] + margin * image.xRes,
              yMax=g.bounds[3] - margin * image.yRes)

    # UTM South vs. UTM North ?
    utm_offset = 0
    target_epsg = int(roi['EPSG'][0])
    target_srs = osr.SpatialReference()
    target_srs.ImportFromEPSG(target_epsg)
    image_srs = osr.SpatialReference(wkt=image.projection)
    image_epsg = image_srs.GetAuthorityCode(None)
    if not target_srs.IsSame(image_srs):
        if image_srs.GetUTMZone() == - target_srs.GetUTMZone():
            # UTM South vs. UTM North case
            utm_offset = 10000000
        else:
            # Not handled
            msg = 'image epsg and target epsg differ: {} / {}. Impossible to reframe input image.'.format(image_epsg,
                                                                                                          target_epsg)
            raise BaseException(msg)

    # compute offsets (grid origin + dx/dy
    if compute_offsets:
        r_dx = image.xRes * (((box.xMin - image.xMin) / image.xRes) % 1)
        r_dy = image.yRes * (((box.yMin - image.yMin) / image.yRes) % 1)
    else:
        r_dx = r_dy = 0

    # compute offsets (grid origin + dx/dy)
    xOff = (box.xMin - image.xMin + dx) / image.xRes
    yOff = (box.yMax - utm_offset - image.yMax - dy) / image.yRes

    # compute target size
    xSize = int(ceil((box.xMax - box.xMin) / image.xRes))
    ySize = int(ceil((box.yMax - box.yMin) / -image.yRes))

    # read image
    array = image.array
    if dtype is None:
        dtype = array.dtype

    if xOff == 0 and yOff == 0 and image.xSize == xSize and image.ySize == ySize:
        new = array
    else:
        # translate and reframe (order= 0:nearest, 1: linear, 3:cubic)
        tf = SimilarityTransform(translation=(xOff, yOff))
        new = skit_warp(array, inverse_map=tf, output_shape=(ySize, xSize), order=order, preserve_range=True)

    # set into new S2L_ImageFile
    return image.duplicate(filepath_out, array=new.astype(dtype), origin=(box.xMin + r_dx, box.yMax + r_dy),
                           output_EPSG=target_epsg)


def reframeMulti(filepath_in, tilecode, filepath_out, dx=0., dy=0., order=3):

    # get roi from mgrs tilecode
    converter = grids.GridsConverter()
    roi = converter.getROIfromMGRS(tilecode)
    converter.close()
    log.debug(roi)

    # load wkt
    g = loads(roi['UTM_WKT'][0])
    Box = namedtuple('Box', ['xMin', 'yMin', 'xMax', 'yMax'])
    box = Box(xMin=g.bounds[0], yMin=g.bounds[1], xMax=g.bounds[2], yMax=g.bounds[3])

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
    target_epsg = int(roi['EPSG'][0])
    target_srs = osr.SpatialReference()
    target_srs.ImportFromEPSG(target_epsg)
    image_srs = osr.SpatialReference(wkt=projection)
    image_epsg = image_srs.GetAuthorityCode(None)
    if not target_srs.IsSame(image_srs):
        if image_srs.GetUTMZone() == - target_srs.GetUTMZone():
            # UTM South vs. UTM North case
            utm_offset = 10000000
        else:
            # Not handled
            msg = 'image epsg and target epsg differ: {} / {}. Impossible to reframe input image.'.format(image_epsg,
                                                                                                          target_epsg)
            raise BaseException(msg)

    # compute offsets
    xOff = (box.xMin - xMin + dx) / xRes
    yOff = (box.yMax - utm_offset - yMax - dy) / yRes

    xSize = int(ceil((box.xMax - box.xMin) / xRes))
    ySize = int(ceil((box.yMax - box.yMin) / -yRes))

    # read image for each band
    for i in range(1, ds_src.RasterCount + 1):
        array = ds_src.GetRasterBand(i).ReadAsArray()

        # translate and reframe
        tf = SimilarityTransform(translation=(xOff, yOff))
        new = skit_warp(array, inverse_map=tf, output_shape=(ySize, xSize), order=order, preserve_range=True)

        if i == 1:
            # write with gdal
            driver = gdal.GetDriverByName('GTiff')
            ds_dst = driver.Create(filepath_out, xsize=xSize, ysize=ySize,
                                   bands=ds_src.RasterCount, eType=gdal.GDT_Int16)
            ds_dst.SetProjection(target_srs.ExportToWkt())
            geotranform = (box.xMin, xRes, 0, box.yMax, 0, yRes)
            log.debug(geotranform)
            ds_dst.SetGeoTransform(geotranform)

        # write band
        ds_dst.GetRasterBand(i).WriteArray(new)
    ds_dst.FlushCache()
    ds_src = None
    ds_dst = None

    return xOff, yOff


def reframe_gdal(imagein, tilecode, imageout):
    # get roi from mgrs tilecode
    converter = grids.GridsConverter()
    roi = converter.getROIfromMGRS(tilecode)
    converter.close()
    log.debug(roi)

    # from roi create geojson
    json = os.path.splitext(imageout)[0] + '.json'
    log.debug(json)
    converter.WktToJson2(roi['UTM_WKT'][0], roi['EPSG'][0], json)

    # crop to cutline with gdalwarp
    rc = gdal.Warp(imageout, imagein, targetAlignedPixels=True, xRes=30, yRes=30, resampleAlg='cubic', dstNoData=0,
                   cropToCutline=True, cutlineDSName=json)

    # catch GDAL error
    if rc != 0:
        raise BaseException
