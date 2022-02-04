#! /usr/bin/env python
# -*- coding: utf-8 -*-
# M. Arthaud (TPZ) 2021

import logging
import numpy as np

from core import S2L_config
from s2l_processes.S2L_Process import S2L_Process
from core.QI_MTD.mtd import metadata

log = logging.getLogger("Sen2Like")


class S2L_InterCalibration(S2L_Process):
    """
    Coefficiant format example:
    {
        "Sentinel-2B": {
            'B01': {'coef': [0.9959, -0.0002]},
            'B02': {'coef': [0.9778, -0.004]},
            'B03': {'coef': [1.0053, -0.0009]},
            'B04': {'coef': [0.9765, 0.0009]},
            'B8A': {'coef': [0.9983, -0.0001]},
            'B11': {'coef': [0.9987, -0.0011]},
            'B12': {'coef': [1.003, -0.0012]},
        }
    }
    Currently possible mission names are : Sentinel-2B, Sentinel-2A, LANDSAT_8, LANDSAT_9
    (It is the SPACECRAFT_NAME (for sentinel) or SPACECRAFT_ID (for landsats))
    """

    def process(self, product, image, band):
        log.info('Start')
        coeff = {
            "Sentinel-2B": {
                'B01': {'coef': [1.011, 0]},
                'B02': {'coef': [1.011, 0]},
                'B03': {'coef': [1.011, 0]},
                'B04': {'coef': [1.011, 0]},
                'B05': {'coef': [1.011, 0]},
                'B06': {'coef': [1.011, 0]},
                'B07': {'coef': [1.011, 0]},
                'B08': {'coef': [1.011, 0]},
                'B8A': {'coef': [1.011, 0]},
            }
        }
        if product.mtl.mission in coeff:
            if band in coeff[product.mtl.mission]:
                slope, offset = coeff[product.mtl.mission][band]['coef']
            else:
                log.info("No inter calibration coefficient defined for {}".format(band))
                log.info('End')
                return image
        else:
            log.info("No inter calibration coefficient defined for {} mission".format(product.mtl.mission))
            log.info('End')
            return image

        if offset is not None and slope is not None:
            log.debug(f"Applying InterCalibration : slope = {slope}, offset{offset}")
            new = image.array
            np.multiply(new, slope, out=new)
            np.add(new, offset, out=new)
            # transfer no data
            new[image.array == 0] = 0
            # Format Output : duplicate, link  to product as parameter
            image = image.duplicate(self.output_file(product, band), array=new.astype(np.float32))
            if S2L_config.config.getboolean('generate_intermediate_products'):
                image.write(creation_options=['COMPRESS=LZW'])

        log.info('End')
        return image
