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
"""Prisma product reader module"""
from datetime import datetime, timedelta

import h5py
import numpy as np
from dateutil import parser, tz
from geometry import LatLong
from numpy.typing import NDArray
from utils import utc_format

PrismaProductFile = h5py.File


class PrismaDate:
    # pylint: disable=too-few-public-methods
    """Class to have date in multiple format"""

    def __init__(self, b_date):
        self.raw: str = b_date.decode("UTF-8")
        self.as_datetime: datetime = parser.parse(self.raw).replace(tzinfo=tz.tzutc())
        self.as_iso_utc: str = utc_format(self.as_datetime)


class PrismaProduct:
    """PRISMA product class"""

    _product_start_time: PrismaDate = None
    _product_stop_time: PrismaDate = None
    _processing_date: PrismaDate = None
    _acquisition_station: str = None
    _processing_station: str = None
    _sun_azimuth_angle: float = None
    _sun_zenith_angle: float = None
    _sun_earth_correction: float = None
    _cloudy_pixel_percentage: float = None

    def __init__(self, file_path):
        self.file_path: str = file_path
        self.product: h5py.File = h5py.File(file_path, "r")
        self._global_attr: h5py.AttributeManager = self.product.attrs
        self._raster = None

    def _get_date_attr(self, attr: str, field: str) -> PrismaDate:
        # get (set it if not yet setted) date attr reading from global product attributes
        if getattr(self, attr) is None:
            setattr(self, attr, PrismaDate(self._global_attr.get(field)))

        return getattr(self, attr)

    def _get_attr(self, attr: str, field: str):
        # get (set it if not yet setted) attr reading from global product attributes
        if getattr(self, attr) is None:
            setattr(self, attr, self._global_attr.get(field))

        return getattr(self, attr)

    @property
    def sun_earth_correction(self) -> float:
        return self._sun_earth_correction

    @sun_earth_correction.setter
    def sun_earth_correction(self, val: float):
        self._sun_earth_correction = val

    @property
    def raster(self):
        return self._raster

    @raster.setter
    def raster(self, raster):
        self._raster = raster

    @property
    def product_start_time(self) -> PrismaDate:
        """Get product sensing UTC start date.
        This property is set at first access by checking if 'None'.
        So it lots of access must be done to this property, use a temp var for performance purpose

        Returns:
            PrismaDate: sensing_start_date
        """
        return self._get_date_attr("_product_start_time", "Product_StartTime")

    @property
    def product_stop_time(self) -> PrismaDate:
        """Get product sensing UTC stop date.
        This property is set at first access by checking if 'None'.
        So it lots of access must be done to this property, use a temp var for performance purpose

        Returns:
            PrismaDate: sensing_stop_date
        """
        return self._get_date_attr("_product_stop_time", "Product_StopTime")

    @property
    def processing_date(self) -> PrismaDate:
        """Get product processing UTC date.
        This property is set at first access by checking if 'None'.
        So it lots of access must be done to this property, use a temp var for performance purpose

        Returns:
            PrismaDate: processing_date
        """
        return self._get_date_attr("_processing_date", "Processing_Time")

    @property
    def processing_centre(self) -> str:
        """Get processing station.
        This property is set at first access by checking if 'None'.
        So it lots of access must be done to this property, use a temp var for performance purpose

        Returns:
            str: processing_centre
        """
        return self._get_attr("_processing_station", "Processing_Station").decode("UTF-8")

    @property
    def acquisition_station(self) -> str:
        """Get acquisition station.
        This property is set at first access by checking if 'None'.
        So it lots of access must be done to this property, use a temp var for performance purpose

        Returns:
            str: acquisition_station
        """
        return self._get_attr("_acquisition_station", "Acquisition_Station").decode("UTF-8")

    @property
    def sun_azimuth_angle(self) -> float:
        """Get sun azimuth angle.
        This property is set at first access by checking if 'None'.
        So it lots of access must be done to this property, use a temp var for performance purpose

        Returns:
            float: sun_azimuth_angle
        """
        return self._get_attr("_sun_azimuth_angle", "Sun_azimuth_angle")

    @property
    def sun_zenith_angle(self) -> float:
        """Get sun zenith angle.
        This property is set at first access by checking if 'None'.
        So it lots of access must be done to this property, use a temp var for performance purpose

        Returns:
            float: sun_zenith_angle
        """
        return self._get_attr("_sun_zenith_angle", "Sun_zenith_angle")

    @property
    def cloudy_pixel_percentage(self) -> float:
        return self._get_attr("_cloudy_pixel_percentage", "L1_Quality_CCPerc")

    @property
    def scene_center_coordinates(self) -> LatLong:
        """Get product scene center as lat lon.
        Lat long are read from 'HDFEOS/SWATHS/PRS_L1_HCO/Geolocation Fields/' VNIR dataset

        Returns:
            LatLong: scene center coord
        """
        return LatLong(
            self.product["HDFEOS/SWATHS/PRS_L1_HCO/Geolocation Fields/Latitude_VNIR"][499, 499],
            self.product["HDFEOS/SWATHS/PRS_L1_HCO/Geolocation Fields/Longitude_VNIR"][499, 499],
        )

    @property
    def scene_center_date(self) -> datetime:
        """Get product scene center UTC date and time.
        Time info is read from 'HDFEOS/SWATHS/PRS_L1_HCO/Time/' VNIR dataset

        Returns:
            datetime: scene center UTC date and time
        """
        time = self.product["HDFEOS/SWATHS/PRS_L1_HCO/Geolocation Fields/Time"][499]
        # time is MJD2000 so add it as days to 2000/1/1 to "real" date time
        return (datetime(2000, 1, 1, 0, 0) + timedelta(days=time)).replace(tzinfo=tz.tzutc())

    def _get_mask_grid(self, path) -> NDArray | None:
        grid = self.product.get(path)
        if grid:
            return np.array(grid)
        return None

    @property
    def cloud_mask_grid(self) -> NDArray | None:
        """Return product mask grid

        Note : This Data Filed is not always present in the L1 Earth Observation Product:
        if any of the bands required for the classification of cloudy pixels is not found in the L0a input file,
        the calculation of this mask is not performed and the corresponding Data Filed is not written in the L1 product.

        0 for not cloudy pixel
        1 for cloudy pixel
        10 = for not of all previous classification
        255 = error
        In case of grouping the number of FOV
        pixel is reduced of a factor 2 or 4.

        Returns:
            NDArray|None: mask grid if present in the product
        """
        return self._get_mask_grid("HDFEOS/SWATHS/PRS_L1_HCO/Data Fields/Cloud_Mask")

    @property
    def land_mask_grid(self) -> NDArray | None:
        """Return product land cover mask grid

        Note: This Data Filed is not always present in the L1 Earth Observation Product:
        if any of the bands required for the classification of the pixels is not found in the L0a input file,
        the calculation of this mask is not performed and the corresponding Data Filed is not written in the L1 product.

        0 for water pixel
        1 for snow pixel (and ice)
        2 for not-vegetated land pixel :bare soil)
        3 for crop and rangeland pixel
        4 for forst pixel
        5 for wetland pixel
        6 for not-vegetated land pixel :urban component
        10 = for not of all previous classification
        255 = error
        In case of grouping the number of FOV
        pixel is reduced of a factor 2 or 4.

        Returns:
            NDArray|None: mask grid if present in the product
        """
        return self._get_mask_grid("HDFEOS/SWATHS/PRS_L1_HCO/Data Fields/LandCover_Mask")

    @property
    def lat_lon_grids(self) -> (NDArray, NDArray):
        """Get original lat lon grids, col/row oriented.
        Client should probably rotate them counterclockwize for row/col usage

        Returns:
            tuple: lat lon grids
        """
        return (
            np.array(self.product["HDFEOS/SWATHS/PRS_L1_HCO/Geolocation Fields/Latitude_VNIR"]),
            np.array(self.product["HDFEOS/SWATHS/PRS_L1_HCO/Geolocation Fields/Longitude_VNIR"]),
        )
