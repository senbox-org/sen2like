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
"""Sentinel 2 L1 like product module"""
from datetime import datetime

from adapter import AngleGrid, MaskFileDef, MeanAngle, ProductAdapter
from osgeo import osr

YYYYMMDDTHHMMSS = "%Y%m%dT%H%M%S"

# Possible Masks
MASK_TABLE = [
    MaskFileDef("MSK_DETFOO", "0", "MSK_DETFOO_B01.jp2"),
    MaskFileDef("MSK_QUALIT", "0", "MSK_QUALIT_B01.jp2"),
    MaskFileDef("MSK_DETFOO", "1", "MSK_DETFOO_B02.jp2"),
    MaskFileDef("MSK_QUALIT", "1", "MSK_QUALIT_B02.jp2"),
    MaskFileDef("MSK_DETFOO", "2", "MSK_DETFOO_B03.jp2"),
    MaskFileDef("MSK_QUALIT", "2", "MSK_QUALIT_B03.jp2"),
    MaskFileDef("MSK_DETFOO", "3", "MSK_DETFOO_B04.jp2"),
    MaskFileDef("MSK_QUALIT", "3", "MSK_QUALIT_B04.jp2"),
    MaskFileDef("MSK_DETFOO", "4", "MSK_DETFOO_B05.jp2"),
    MaskFileDef("MSK_QUALIT", "4", "MSK_QUALIT_B05.jp2"),
    MaskFileDef("MSK_DETFOO", "5", "MSK_DETFOO_B06.jp2"),
    MaskFileDef("MSK_QUALIT", "5", "MSK_QUALIT_B06.jp2"),
    MaskFileDef("MSK_DETFOO", "6", "MSK_DETFOO_B07.jp2"),
    MaskFileDef("MSK_QUALIT", "6", "MSK_QUALIT_B07.jp2"),
    MaskFileDef("MSK_DETFOO", "7", "MSK_DETFOO_B08.jp2"),
    MaskFileDef("MSK_QUALIT", "7", "MSK_QUALIT_B08.jp2"),
    MaskFileDef("MSK_DETFOO", "8", "MSK_DETFOO_B8A.jp2"),
    MaskFileDef("MSK_QUALIT", "8", "MSK_QUALIT_B8A.jp2"),
    MaskFileDef("MSK_DETFOO", "9", "MSK_DETFOO_B09.jp2"),
    MaskFileDef("MSK_QUALIT", "9", "MSK_QUALIT_B09.jp2"),
    MaskFileDef("MSK_DETFOO", "10", "MSK_DETFOO_B10.jp2"),
    MaskFileDef("MSK_QUALIT", "10", "MSK_QUALIT_B10.jp2"),
    MaskFileDef("MSK_DETFOO", "11", "MSK_DETFOO_B11.jp2"),
    MaskFileDef("MSK_QUALIT", "11", "MSK_QUALIT_B11.jp2"),
    MaskFileDef("MSK_DETFOO", "12", "MSK_DETFOO_B12.jp2"),
    MaskFileDef("MSK_QUALIT", "12", "MSK_QUALIT_B12.jp2"),
    MaskFileDef("MSK_CLASSI", None, "MSK_CLASSI_B00.tif"),
]


BAND_LIST = [
    "B01",
    "B02",
    "B03",
    "B04",
    "B05",
    "B06",
    "B07",
    "B08",
    "B8A",
    "B09",
    "B10",
    "B11",
    "B12",
]


class Sen2LikeProduct:
    """
    Sen2like L1C representation object class.
    This class use 'ProductAdapter' to access input product information adapted for sen2like level product.
    """

    # S2P_MSIL1C_20220822T175909_N0400_R041_T12SYH_20220822T201139.SAFE
    _safe_name_tpl = "{}_MSIL1C_{}_N{}_R{}_T{}_{}.SAFE"

    # S2B_OPER_MSI_L1C_DS_2BPS_20220822T201139_S20220822T180505_N04.00
    _datastrip_identifier_tpl = "{}_OPER_MSI_{}_DS_{}_{}_S{}_N{}"

    # GS2B_20220822T175909_028524_N04.00
    _datatake_identifier_tpl = "G{}_{}_{}_N{}"

    # S2B_OPER_MSI_L1C_TL_2BPS_20220822T201139_A028524_T12SYH_N04.00
    _long_granule_identifier_tpl = "{}_OPER_MSI_{}_TL_{}_{}_A{}_T{}_N{}"

    # L1C_T12SYH_A028524_20220822T180505
    _short_granule_identifier_tpl = "{}_T{}_A{}_{}"

    # T12SYH_20220822T175909_B01
    _image_filename_tpl = "T{}_{}_{}"

    _processing_baseline = "0000"
    _processing_baseline_dotted = "00.00"

    def __init__(self, adapter: ProductAdapter):
        self._product_adapter: ProductAdapter = adapter
        self._product_date = datetime.utcnow()
        # bands image files by band name
        self._band_files = {}

    @property
    def datatake_identifier(self):
        # GS2B_20220822T175909_028524_N04.00
        return self._datatake_identifier_tpl.format(
            self._product_adapter.platform,
            self._product_adapter.datatake_sensing_time.strftime(YYYYMMDDTHHMMSS),
            "{:06}".format(self._product_adapter.absolute_orbit_number),
            self._processing_baseline_dotted,
        )

    @property
    def product_name(self) -> str:
        """Get SAFE product name.
        Example: S2P_MSIL1C_20220822T175909_N0400_R041_T12SYH_20220822T201139.SAFE

        Returns:
            str: SAFE name
        """

        return self._safe_name_tpl.format(
            self._product_adapter.platform,
            self._product_adapter.datatake_sensing_time.strftime(YYYYMMDDTHHMMSS),
            self._processing_baseline,
            "{:03}".format(self._product_adapter.sensing_orbit_number),
            self._product_adapter.tile_number,
            self._product_date.strftime(YYYYMMDDTHHMMSS),
        )

    @property
    def datastrip_identifier(self) -> str:
        """Get datastrip identifier.
        Example: S2B_OPER_MSI_L1C_DS_2BPS_20220822T201139_S20220822T180505_N04.00

        Returns:
            str: datastrip identifier
        """
        # sensor 3 chars
        # level 3 chars
        # station 4 chars
        return self._datastrip_identifier_tpl.format(
            self._product_adapter.platform,
            self._product_adapter.shot_level,
            self._product_adapter.processing_center,
            self._product_date.strftime(YYYYMMDDTHHMMSS),
            self.product_start_time.strftime(YYYYMMDDTHHMMSS),
            self._processing_baseline_dotted,
        )

    @property
    def long_granule_identifier(self) -> str:
        # S2B_OPER_MSI_L1C_TL_2BPS_20220822T201139_A028524_T12SYH_N04.00

        return self._long_granule_identifier_tpl.format(
            self._product_adapter.platform,
            self._product_adapter.shot_level,
            self._product_adapter.station,  # TODO, which one, then remove from adapter ?
            self._product_date.strftime(YYYYMMDDTHHMMSS),
            "{:06}".format(self._product_adapter.absolute_orbit_number),
            self._product_adapter.tile_number,
            self._processing_baseline_dotted,
        )

    @property
    def short_granule_identifier(self) -> str:
        # L1C_T12SYH_A028524_20220822T180505

        return self._short_granule_identifier_tpl.format(
            self._product_adapter.shot_level,
            self._product_adapter.tile_number,
            "{:06}".format(self._product_adapter.absolute_orbit_number),
            self._product_adapter.granule_sensing_start.strftime(YYYYMMDDTHHMMSS),
        )

    @property
    def sun_earth_correction(self) -> float:
        return self._product_adapter.sun_earth_correction

    @property
    def pvi_filename(self) -> str:
        return self.get_image_filename("PVI") + ".tif"

    @property
    def tci_filename(self) -> str:
        return self.get_image_filename("TCI") + ".TIF"

    def get_image_filename(self, band: str) -> str:
        return self._image_filename_tpl.format(
            self._product_adapter.tile_number,
            self._product_adapter.granule_sensing_start.strftime(YYYYMMDDTHHMMSS),
            band,
        )

    @property
    def image_filename_list(self):
        # sample : T12SYH_20220822T175909_B01
        # NOTE : to update only for existing bands using self._band_files
        for band in ["B01", "B02", "B03", "B04", "B05", "B06", "B07", "B08", "B8A", "B09", "B10", "B11", "B12", "TCI"]:
            yield self.get_image_filename(band)

    def get_mask_file(self, mask_file_def: MaskFileDef) -> str | None:
        """Get mask file path from the given definition

        Args:
            mask_file_def (MaskFileDef): mask definition

        Returns:
            str|None: mask file path. None if not exists
        """
        return self._product_adapter.get_mask_file(mask_file_def)

    def get_band_file(self, band_name: str) -> str:
        return self._product_adapter.get_band_file(band_name)

    @property
    def spacecraft(self) -> str:
        return self._product_adapter.spacecraft

    @property
    def baseline(self) -> str:
        return self._processing_baseline_dotted

    @property
    def archiving_center(self) -> str:
        return self._product_adapter.archiving_center

    @property
    def reception_station(self) -> str:
        return self._product_adapter.reception_station

    @property
    def processing_center(self) -> str:
        return self._product_adapter.processing_center

    @property
    def processing_time(self):
        return self._product_adapter.processing_time

    @property
    def product_date(self) -> str:
        return self._product_date

    @property
    def product_start_time(self) -> datetime:
        return self._product_adapter.product_start_time

    @property
    def product_stop_time(self) -> datetime:
        return self._product_adapter.product_stop_time

    @property
    def datatake_sensing_start(self) -> datetime:
        return self._product_adapter.datatake_sensing_start

    @property
    def datastrip_sensing_start(self) -> datetime:
        return self._product_adapter.datastrip_sensing_start

    @property
    def datastrip_sensing_stop(self) -> datetime:
        return self._product_adapter.datastrip_sensing_stop

    @property
    def sensing_orbit_number(self) -> int:
        return self._product_adapter.sensing_orbit_number

    @property
    def sensing_orbit_direction(self) -> int:
        return self._product_adapter.sensing_orbit_direction

    @property
    def processing_level(self) -> str:
        return self._product_adapter.processing_level

    @property
    def tile_sensing_time(self) -> datetime:
        return self._product_adapter.tile_sensing_time

    @property
    def mean_sun_angle(self) -> MeanAngle:
        return self._product_adapter.mean_sun_angle

    @property
    def mean_viewing_angle(self) -> MeanAngle:
        return self._product_adapter.mean_viewing_angle

    @property
    def sun_angle_grid(self) -> AngleGrid:
        return self._product_adapter.sun_angle_grid

    @property
    def tile(self):
        return self._product_adapter.tile_number

    @property
    def viewing_angle_grid(self):
        return self._product_adapter.viewing_angle_grid

    @property
    def cloudy_pixel_percentage(self) -> float:
        return self._product_adapter.cloudy_pixel_percentage

    @property
    def snow_pixel_percentage(self) -> float:
        return self._product_adapter.snow_pixel_percentage

    @property
    def ulx(self) -> int:
        return int(self._product_adapter.tile_info.geometry.bounds[0])

    @property
    def uly(self) -> int:
        return int(self._product_adapter.tile_info.geometry.bounds[3])

    @property
    def epsg_code(self) -> str:
        return self._product_adapter.tile_info.epsg

    @property
    def epsg_name(self) -> str:
        srs = osr.SpatialReference()
        srs.ImportFromEPSG(int(self.epsg_code))
        # WGS84 / UTM zone 12N
        return srs.GetAttrValue("projcs")
