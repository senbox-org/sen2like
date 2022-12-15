#! /usr/bin/env python
# -*- coding: utf-8 -*-
# V. Debaecker (TPZ-F) 2018

import logging

from core import S2L_config
from core.image_file import S2L_ImageFile
from core.products.product import S2L_Product
from s2l_processes.S2L_Process import S2L_Process
from core.toa_reflectance import convert_to_reflectance_from_reflectance_cal_product

log = logging.getLogger("Sen2Like")


class S2L_Toa(S2L_Process):

    def process(self, product: S2L_Product, image: S2L_ImageFile, band: str) -> S2L_ImageFile:
        log.info('Start')

        # convert to TOA (gain + offset)
        array_in = image.array
        array_out = convert_to_reflectance_from_reflectance_cal_product(product.mtl, array_in, band)
        image = image.duplicate(self.output_file(product, band), array=array_out)
        if S2L_config.config.getboolean('generate_intermediate_products'):
            image.write(creation_options=['COMPRESS=LZW'])

        log.info('End')

        return image
