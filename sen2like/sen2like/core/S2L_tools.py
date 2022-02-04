#! /usr/bin/env python
# -*- coding: utf-8 -*-
# V. Debaecker (TPZ-F) 2018

import logging
import os

import numpy as np
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

    # Grayscale or RGB
    if len(bands) == 1:
        band_list = [1]
    else:
        band_list = [1, 2, 3]

    # create single vrt with B4 B3 B2
    vrtpath = qlpath + '.vrt'

    gdal.BuildVRT(vrtpath, imagefiles, separate=True)
    log.debug("save in : " + vrtpath)

    # Remove nodata attribut
    vrt = gdal.Open(vrtpath, gdal.GA_Update)
    for i in band_list:
        vrt.GetRasterBand(i).DeleteNoDataValue()
    del vrt
    # convert to JPEG (with scaling)
    # TODO: DN depend on the mission, the level of processing...

    # default
    src_min = 0
    #src_min = 1
    src_max = 2500
    dst_min = 0
    #dst_min = 1
    dst_max = 255
    if bands == ["B12", "B11", "B8A"]:
        src_max = 4000

    # FIXME: site specific should be in configuration
    if pd.mtl.mgrs == '34RGS':
        src_max = 4000
        if bands == ["B12", "B11", "B8A"]:
            src_max = 10000

    scale = [[src_min, src_max, dst_min, dst_max]]

    # do gdal...
    if format == 'GTIFF':
        co = creationOptions  # Because the driver does not support QUALITY={quality} as co when format='Gtiff'
    else:
        co = [f'QUALITY={quality}'] if creationOptions is None else [f'QUALITY={quality}'] + creationOptions
    gdal.Translate(qlpath, vrtpath, xRes=xRes, yRes=yRes, resampleAlg='bilinear', bandList=band_list,
                   outputType=gdal.GDT_Byte, format=format, creationOptions=co,
                   scaleParams=scale)
    log.info("save in : {}".format(qlpath))

    quantification_value = 10000.
    scaling = (src_max - src_min) / quantification_value / (dst_max - dst_min)
    offset = 0

    try:
        dataset = gdal.Open(qlpath)
        for i in band_list:
            dataset.GetRasterBand(i).SetScale(scaling)
            dataset.GetRasterBand(i).SetOffset(offset)
            dataset.GetRasterBand(i).DeleteNoDataValue()
        log.info("scale and offset information added to the metadata of the quicklook image")

    except Exception as e:
        log.warning(e, exc_info=True)
        log.warning('error updating the metadata of quicklook image')

    # clean
    os.remove(vrtpath)


def out_stat(input_matrix, logger, label=""):
    logger.debug('Maximum {} : {}'.format(label, np.max(input_matrix)))
    logger.debug('Mean {} : {}'.format(label, np.mean(input_matrix)))
    logger.debug('Std dev {} : {}'.format(label, np.std(input_matrix)))
    logger.debug('Minimum {} : {}'.format(label, np.min(input_matrix)))
