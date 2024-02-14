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

log = logging.getLogger("Sen2Like")


def convert_to_reflectance_from_reflectance_cal_product(mtl, data_in, band):
    """Applied conversion to TOA reflectance, assuming product is calibrated
    in reflectance as S2 MSI and LS8 OLI
    Required mtl.processing_dic, a dictionary including the list of band
    to be processing"""

    log.debug("Conversion to TOA")

    reflectance_data = None
    if mtl.sensor in ('OLI', 'OLI_TIRS'):
        # LANDSAT 8
        log.info("Sun Zenith angle : %s deg", mtl.sun_zenith_angle)
        sun_elevation_angle = 90. - mtl.sun_zenith_angle
        log.info("Sun Elevation angle : %s deg", sun_elevation_angle)

        gain = offset = None
        for k, x in list(mtl.radio_coefficient_dic.items()):
            if 'B' + x['Band_id'] == band:
                gain = str(x['Gain'])
                offset = str(x['Offset'])
                log.info('Band Id : %s Gain : %s / Offset : %s', x['Band_id'], gain, offset)
        if gain is not None and offset is not None:
            if 'L2' in mtl.data_type:  # Level-2 product surface reflectance is independent from sun_elevation_angle
                reflectance_data = (np.float32(data_in) * np.float32(gain) + np.float32(offset))
            else:
                reflectance_data = (np.float32(data_in) * np.float32(gain) + np.float32(offset)) / np.sin(
                sun_elevation_angle * np.pi / 180.)
            mask = (data_in <= 0)
            reflectance_data[mask] = 0
        elif band in ('B10', 'B11'):
            offset = float(S2L_config.config.get('offset'))
            gain = float(S2L_config.config.get('gain'))
            reflectance_data = np.float32(data_in) / gain - offset
            mask = (data_in <= 0)
            reflectance_data[mask] = 0

    elif mtl.sensor == 'MSI':

        if mtl.radiometric_offset_dic is not None:
            radio_add_offset = mtl.radiometric_offset_dic[mtl.band_names.index(band)]
            reflectance_data = (np.float32(data_in) + np.float32(radio_add_offset)) / float(mtl.quantification_value)
        else:
            reflectance_data = np.float32(data_in) / float(mtl.quantification_value)

    return reflectance_data
