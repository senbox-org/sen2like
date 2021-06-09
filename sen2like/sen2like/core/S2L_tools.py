#! /usr/bin/env python
# -*- coding: utf-8 -*-
# V. Debaecker (TPZ-F) 2018

import logging
import os

from osgeo import gdal

log = logging.getLogger("Sen2Like")


def quicklook(pd, images, bands, qlpath, quality=95, xRes=30, yRes=30, format='JPEG', creationOptions: list = None):
    """

    :param pd: S2L_Product object
    :param images: list of image filepaths
    :param bands: List of 3 band index for [R, G, B]
    :param qlpath: output file path
    :return:
    """

    imagefiles = []

    # bands for rgb
    for band in bands:
        if band not in images.keys():
            log.warning('Bands not available for quicklook ({})'.format(bands))
            return None
        else:
            imagefiles.append(images[band])

    # create output directory if it does not exist
    qldir = os.path.dirname(qlpath)
    if not os.path.exists(qldir):
        os.makedirs(qldir)

    # create single vrt with B4 B3 B2
    vrtpath = qlpath + '.vrt'

    gdal.BuildVRT(vrtpath, imagefiles, separate=True)
    log.debug("save in : " + vrtpath)

    # convert to JPEG (with scaling)
    # TODO: DN depend on the mission, the level of processing...

    # default
    src_min = 0.
    src_max = 2500
    if bands == ["B12", "B11", "B8A"]:
        src_max = 4000

    # FIXME: site specific should be in configuration
    if pd.mtl.mgrs[-5:] == '34RGS':
        src_max = 4000
        if bands == ["B12", "B11", "B8A"]:
            src_max = 10000
    scale = [[src_min, src_max]]

    # Grayscale or RGB
    if len(bands) == 1:
        band_list = [1]
    else:
        band_list = [1, 2, 3]

    # do gdal...
    if format == 'GTIFF':
        co = creationOptions  # Because the driver does not support QUALITY={quality} as co when format='Gtiff'
    else:
        co = [f'QUALITY={quality}'] if creationOptions is None else [f'QUALITY={quality}'] + creationOptions
    gdal.Translate(qlpath, vrtpath, xRes=xRes, yRes=yRes, resampleAlg='bilinear', bandList=band_list,
                   outputType=gdal.GDT_Byte, format=format, creationOptions=co,
                   noData=0, scaleParams=scale)
    log.info("save in : {}".format(qlpath))

    # clean
    os.remove(vrtpath)
