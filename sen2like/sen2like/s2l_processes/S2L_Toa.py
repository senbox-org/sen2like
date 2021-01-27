#! /usr/bin/env python
# -*- coding: utf-8 -*-
# V. Debaecker (TPZ-F) 2018

import logging

import numpy as np

from core.S2L_config import config
from s2l_processes.S2L_Process import S2L_Process

log = logging.getLogger("Sen2Like")


def convert_to_reflectance_from_reflectance_cal_product(mtl, data_in, band):
    """Applied conversion to TOA reflectance, assuming product is calibrated
    in reflectance as S2 MSI and LS8 OLI
    Required mtl.processing_dic, a dictionary including the list of band
    to be processing"""

    log.debug("Conversion to TOA")

    reflectance_data = None
    if mtl.sensor == 'OLI' or mtl.sensor == 'OLI_TIRS':
        # LANDSAT 8
        log.info("Sun Zenith angle : {} deg".format(mtl.sun_zenith_angle))
        sun_elevation_angle = 90. - mtl.sun_zenith_angle
        log.info("Sun Elevation angle : {} deg".format(sun_elevation_angle))

        gain = offset = None
        for k, x in list(mtl.rho_radio_coefficient_dic.items()):
            if 'B' + x['Band_id'] == band:
                gain = str(x['Gain'])
                offset = str(x['Offset'])
                log.info('Band Id : {} Gain : {} / Offset : {}'.format(x['Band_id'], gain, offset))
        if gain is not None and offset is not None:
            reflectance_data = (np.float32(data_in) * np.float32(gain) + np.float32(offset)) / np.sin(
                sun_elevation_angle * np.pi / 180.)
            mask = (data_in <= 0)
            reflectance_data[mask] = 0
        elif band in ('B10', 'B11'):
            offset = float(config.get('offset'))
            gain = float(config.get('gain'))
            reflectance_data = np.float32(data_in) / gain - offset
            mask = (data_in <= 0)
            reflectance_data[mask] = 0

    elif mtl.sensor == 'MSI':
        # apply quantification value
        reflectance_data = np.float32(data_in) / float(mtl.quantification_value)

    return reflectance_data


class S2L_Toa(S2L_Process):
    def __init__(self):
        super().__init__()

    def process(self, product, image, band):
        log.info('Start')

        # convert to TOA (gain + offset)
        array_in = image.array
        array_out = convert_to_reflectance_from_reflectance_cal_product(product.mtl, array_in, band)
        image = image.duplicate(self.output_file(product, band), array=array_out)
        if config.getboolean('generate_intermediate_products'):
            image.write(creation_options=['COMPRESS=LZW'])

        log.info('End')

        return image
