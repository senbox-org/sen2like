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

from core import S2L_config
from core.image_file import S2L_ImageFile
from core.products.product import S2L_Product
from core.toa_reflectance import convert_to_reflectance_from_reflectance_cal_product
from s2l_processes.S2L_Process import S2L_Process

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
