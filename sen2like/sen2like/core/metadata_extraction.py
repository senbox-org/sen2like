#!/usr/bin/python
# -*- coding: utf-8 -*-

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


def compute_earth_solar_distance(doy):
    return 1 - np.multiply(0.016729, np.cos(0.9856 * (doy - 4) * np.divide(np.pi, 180)))


def get_in_band_solar_irrandiance_value(mission, sensor):
    # In band Solar Irrandiance
    log.debug(mission)
    log.debug(sensor)
    if (mission == 'LANDSAT_5') and (sensor == 'MSS'):
        solarIrradiance = [1848, 1588, 1235, 856.6]
    elif ((mission == 'LANDSAT_4') and (
            sensor == 'MSS_4' or sensor == 'MSS')):  # Faire regexp pour les autres Landsat mss
        solarIrradiance = [1848, 1588, 1235, 856.6]
    elif ((mission == 'LANDSAT_3') and (
            sensor == 'MSS_3' or sensor == 'MSS')):  # Faire regexp pour les autres Landsat mss
        solarIrradiance = [1848, 1588, 1235, 856.6]
    elif ((mission == 'LANDSAT_2') and (
            sensor == 'MSS_2' or sensor == 'MSS')):  # Faire regexp pour les autres Landsat mss
        solarIrradiance = [1848, 1588, 1235, 856.6]
    elif ((mission == 'LANDSAT_1') and (
            sensor == 'MSS_1' or sensor == 'MSS')):  # Faire regexp pour les autres Landsat mss
        solarIrradiance = [1848, 1588, 1235, 856.6]
    elif (mission == 'LANDSAT_5') and (sensor == 'TM'):
        solarIrradiance = [1983.0, 1796.0, 1536.0, 1031.0, 220.0, 0.0, 83.44]
    elif (mission == 'LANDSAT_4') and (sensor == 'TM'):
        solarIrradiance = [1983.0, 1796.0, 1536.0, 1031.0, 220.0, 0.0, 83.44]
    elif (mission == 'LANDSAT_7') and (sensor == 'ETM'):
        solarIrradiance = [1970, 1843, 1555, 1047, 227.1, 0, 80.53]
    elif ((mission == 'LANDSAT_8')
          and ((sensor == 'OLI') or
               (sensor == 'OLI_TIRS') or
               (sensor == 'TIRS'))):  # OR TIRS OR OLI_TIRS
        solarIrradiance = [2067, 2067, 1893, 1603, 972.6, 245, 79.72, 0, 399.7, 0, 0]
    elif (mission == 'SENTINEL_2') and (sensor == 'OLCI'):  # SENTINEL2
        solarIrradiance = [1913.57, 1941.63, 1822.61, 1512.79,
                           1425.56, 1288.32, 1163.19, 1036.39,
                           955.19, 813.04, 367.15, 245.59, 85.25]
    else:
        solarIrradiance = 'SOLAR IRRADIANCE NOT_FOUND'
    return solarIrradiance


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
        subs = 'not found'
    return subs


def from_date_to_doy(date):
    # date = raw_input("Enter date: ")  ## format is 02-02-2016
    from datetime import datetime
    adate = datetime.strptime(date, "%d-%m-%Y")
    day_of_year = adate.timetuple().tm_yday
    return day_of_year
