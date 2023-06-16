#!/usr/bin/python
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
import re

import numpy as np

log = logging.getLogger("Sen2Like")

__component_name__ = "metadata-extraction"  # Extract Metadata for Landsat Products (LS01 - LS08)
__author__ = "Sebastien Saunier"
__copyright__ = "Copyright 2017, TPZ"
__version__ = "0.1.0"
__status__ = "Production"  # "Prototype", "Development", or "Production"
description = __component_name__ + " version:" + __version__ + " (" + __status__ + ")"

NOT_FOUND = 'not found'


def compute_earth_solar_distance(doy):
    return 1 - np.multiply(0.016729, np.cos(0.9856 * (doy - 4) * np.divide(np.pi, 180)))


def get_in_band_solar_irrandiance_value(mission, sensor):
    # In band Solar Irrandiance
    log.debug(mission)
    log.debug(sensor)
    if mission == 'LANDSAT_5' and sensor == 'MSS':
        solar_irradiance = [1848, 1588, 1235, 856.6]
    elif mission == 'LANDSAT_4' and sensor in ('MSS_4', 'MSS'):  # Faire regexp pour les autres Landsat mss
        solar_irradiance = [1848, 1588, 1235, 856.6]
    elif mission == 'LANDSAT_3' and sensor in ('MSS_3', 'MSS'):  # Faire regexp pour les autres Landsat mss
        solar_irradiance = [1848, 1588, 1235, 856.6]
    elif mission == 'LANDSAT_2' and sensor in ('MSS_2', 'MSS'):  # Faire regexp pour les autres Landsat mss
        solar_irradiance = [1848, 1588, 1235, 856.6]
    elif mission == 'LANDSAT_1' and sensor in ('MSS_1', 'MSS'):  # Faire regexp pour les autres Landsat mss
        solar_irradiance = [1848, 1588, 1235, 856.6]
    elif mission == 'LANDSAT_5' and sensor == 'TM':
        solar_irradiance = [1983.0, 1796.0, 1536.0, 1031.0, 220.0, 0.0, 83.44]
    elif mission == 'LANDSAT_4' and sensor == 'TM':
        solar_irradiance = [1983.0, 1796.0, 1536.0, 1031.0, 220.0, 0.0, 83.44]
    elif mission == 'LANDSAT_7' and sensor == 'ETM':
        solar_irradiance = [1970, 1843, 1555, 1047, 227.1, 0, 80.53]
    elif mission in ('LANDSAT_8', 'LANDSAT8') and sensor in ('OLI', 'OLI_TIRS', 'OLITIRS', 'TIRS'):
        solar_irradiance = [2067, 2067, 1893, 1603, 972.6, 245, 79.72, 0, 399.7, 0, 0]
    elif mission == 'SENTINEL_2' and sensor == 'OLCI':  # SENTINEL2
        solar_irradiance = [1913.57, 1941.63, 1822.61, 1512.79,
                            1425.56, 1288.32, 1163.19, 1036.39,
                            955.19, 813.04, 367.15, 245.59, 85.25]
    else:
        solar_irradiance = 'SOLAR IRRADIANCE NOT_FOUND'
    return solar_irradiance


def getTimeZeroValue(mission):
    if mission == 'LANDSAT_5':  # Faire regexp pour les autres Landsat mss
        timeZeroValue = 1984.207
    elif mission == 'LANDSAT_7':
        timeZeroValue = 1999.3
    elif mission == 'LANDSAT_8':
        timeZeroValue = 2015  # m(TBC)
    else:
        timeZeroValue = 'NOT_FOUND'
    return timeZeroValue


def reg_exp(mtl_text, stringToSearch):
    regex = re.compile(stringToSearch)
    result = regex.findall(mtl_text)
    if result:
        subs = result[0].split('=')[1].replace('"', '').replace(' ', '')
    else:
        subs = NOT_FOUND
    return subs


def from_date_to_doy(date):
    # date = raw_input("Enter date: ")  ## format is 02-02-2016
    from datetime import datetime
    adate = datetime.strptime(date, "%d-%m-%Y")
    day_of_year = adate.timetuple().tm_yday
    return day_of_year
