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


import logging

import numpy as np

from core import S2L_config
from core.image_file import S2L_ImageFile
from core.products.product import S2L_Product
from s2l_processes.S2L_Process import S2L_Process

log = logging.getLogger("Sen2Like")

COEFFICIENT = {
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

    def process(self, product: S2L_Product, image: S2L_ImageFile, band: str) -> S2L_ImageFile:
        log.info('Start')

        if product.mtl.mission in COEFFICIENT:
            if float(product.mtl.processing_sw) < 4.0:
                if band in COEFFICIENT[product.mtl.mission]:
                    slope, offset = COEFFICIENT[product.mtl.mission][band]['coef']
                else:
                    log.info("No inter calibration coefficient defined for %s", band)
                    log.info('End')
                    return image
            else:
                log.info("No inter calibration performed for Sentinel-2B Collection-1 products (PB >= 04.00) ")
                log.info('End')
                return image
        else:
            log.info("No inter calibration coefficient defined for %s mission", product.mtl.mission)
            log.info('End')
            return image

        if offset is not None and slope is not None:
            log.debug("Applying InterCalibration : slope = %s, offset = %s", slope, offset)
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
