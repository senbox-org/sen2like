# -*- coding: utf-8 -*-
# Copyright (c) 2023 ESA.
#
# This file is part of Prisma4sen2like.
# See https://github.com/senbox-org/sen2like/prisma4sen2like for further info.
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
""" MGRS utility module
>>> import mgrs
>>> m = mgrs.MGRS()
>>> m.toMGRS(41.79915237426758, 12.32413101196289)
'33TTG7768630938'
"""
import mgrs
from geometry import LatLong
from sen2like.grids import GridsConverter, MGRSGeoInfo
from shapely.wkt import loads

_MGRS = mgrs.MGRS()


def get_mgrs_geo_info(tile_code: str) -> MGRSGeoInfo:
    """Get MGRS geo information of the given tile

    Args:
        tile_code (str): mgrs tile code

    Returns:
        MGRSGeoInfo: MGRS info
    """
    converter = GridsConverter()
    roi = converter.getROIfromMGRS(tile_code)
    converter.close()

    return MGRSGeoInfo(roi["TILE_ID"][0], roi["EPSG"][0], loads(roi["UTM_WKT"][0]))


def get_tile(lat_lon: LatLong) -> str:
    """Get tile name of the MGRS tile that contains given lat lon coordinates

    Args:
        lat_lon (LatLong): input coordinates

    Returns:
        str: mgrs tile name
    """
    return _MGRS.toMGRS(lat_lon.lat, lat_lon.lon)[:5]
