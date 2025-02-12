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
import glob
import os
import re
from datetime import datetime

from core.products.product import DATE_WITH_MILLI_FORMAT, ProcessingContext, S2L_Product

logger = logging.getLogger('Sen2Like')

# resolution folder name for band
_L2A_BAND_FOLDER = {
    "B01":  "R60m",
    "B02" : "R10m",
    "B03" : "R10m",
    "B04" : "R10m",
    "B05" : "R20m",
    "B06" : "R20m",
    "B07" : "R20m",
    "B08" : "R10m",
    "B8A" : "R20m",
    "B09" : "R60m",
    "B11" : "R20m",
    "B12" : "R20m",
    "SCL" : "R20m",
    "AOT" : "R10m",
}


_PSD_LOOKUP_TABLE = {
    "04.00": "14",
    "05.00": "14",
    "05.09": "14",
    "05.10": "14",
    "05.11": "15",
}


name_start_expr = re.compile(r'S2[ABCD].*')


class Sentinel2Product(S2L_Product):
    sensor = 'S2'
    supported_sensors = ('S2A', 'S2B', 'S2C', 'S2D')
    is_final = True  # Indicates if this reader is a final format
    native_bands = ('B05', 'B06', 'B07', 'B08')
    brdf_coefficients = {"B02": {"s2_like_band_label": 'BLUE', "coef": [0.0774, 0.0079, 0.0372]},
                         "B03": {"s2_like_band_label": 'GREEN', "coef": [0.1306, 0.0178, 0.058]},
                         "B04": {"s2_like_band_label": 'RED', "coef": [0.169, 0.0227, 0.0574]},
                         "B08": {"s2_like_band_label": 'NIR', "coef": [0.3093, 0.033, 0.1535]},
                         "B8A": {"s2_like_band_label": 'NIR', "coef": [0.3093, 0.033, 0.1535]},
                         "B11": {"s2_like_band_label": 'SWIR1', "coef": [0.343, 0.0453, 0.1154]},
                         "B12": {"s2_like_band_label": 'SWIR2', "coef": [0.2658, 0.0387, 0.0639]}}
    s2_date_regexp = re.compile(r"S2._.+?_(\d{8}T\d{6})_.*")
    s2_date_regexp_long_name = re.compile(r"S2._.+?_\d{8}T\d{6}_R\d{3}_V(\d{8}T\d{6})_\d{8}T\d{6}.*")
    s2_processing_level_regexp = re.compile(r"S2._([^_]+)_.*")
    # override S2L_Product
    apply_sbaf_param = False
    # override S2L_Product
    # S2 products already in mgrs frame, so that as angle file does need reframing
    reframe_angle_file = False

    def __init__(self, path, context: ProcessingContext):
        super().__init__(path, context)
        self.read_metadata()
        self._dt_sensing_start = None
        self._ds_sensing_start = None
        # override
        self._psd = self._set_psd()

    @classmethod
    def date_format(cls, name):
        if len(name) == 83:
            regexp = cls.s2_date_regexp_long_name
        else:
            regexp = cls.s2_date_regexp
        date_format = "%Y%m%dT%H%M%S"
        return regexp, date_format

    @classmethod
    def processing_level(cls, name):
        match = cls.s2_processing_level_regexp.match(name)
        if match:
            return 'LEVEL2A' if match.group(1)[3:] == 'L2A' else 'LEVEL1C'
        return None

    def band_files(self, band):
        band_path = os.path.join(self.path, 'GRANULE', self.mtl.granule_id, 'IMG_DATA')
        if self.mtl.data_type == 'Level-2A':
            files = glob.glob(
                os.path.join(
                    band_path,
                    _L2A_BAND_FOLDER[band],
                    f'*_{band}_{_L2A_BAND_FOLDER[band][1:]}{self.mtl.file_extension}'
                )
            )
            return files

        return glob.glob(os.path.join(band_path, f'*_{band}{self.mtl.file_extension}'))

    def get_smac_filename(self, band):
        # for S2C and S2D, select S2A cof for now
        sensor = self.sensor_name
        if sensor not in ['S2A', 'S2B']:
            sensor = "S2A"
        # select S2A or S2B coef
        return 'Coef_{}_CONT_{}.dat'.format(self.sensor_name, band.replace('0', '').replace('8A', '8a'))

    def _set_psd(self) -> str:
        min_supported = min(_PSD_LOOKUP_TABLE.keys())
        max_supported = max(_PSD_LOOKUP_TABLE.keys())

        # is baseline known
        if self.mtl.processing_sw not in _PSD_LOOKUP_TABLE.keys():
            logger.warning("Unknow baseline: %s", self.mtl.processing_sw)

        # is baseline supported     
        if self.mtl.processing_sw < min_supported:
            logger.error(
                "Unsupported Baseline: %s, minimum supported is %s",
                self.mtl.processing_sw,
                min_supported
            )
            raise Exception(f"Unsupported Baseline: {self.mtl.processing_sw}")

        _psd = _PSD_LOOKUP_TABLE.get(self.mtl.processing_sw, None)
        # psd found with baseline
        if _psd:
            return _psd

        # psd not found, use latest
        _psd = _PSD_LOOKUP_TABLE.get(max_supported)
        logger.warning("Consider latest PSD %s for baseline %s", _psd, self.mtl.processing_sw)
        return _psd

    @property
    def sensor_name(self):
        # catch S2A | S2B | S2C | S2D
        return self.mtl.product_name[:3]

    @staticmethod
    def can_handle(product_path):
        return name_start_expr.match(os.path.basename(product_path)) is not None

    @property
    def dt_sensing_start(self) -> datetime:
        """S2 Datatake sensing start

        Returns:
            datetime: Datatake sensing start
        """

        if self._dt_sensing_start:
            return self._dt_sensing_start

        self._dt_sensing_start = datetime.strptime(
            self.mtl.dt_sensing_start,
            DATE_WITH_MILLI_FORMAT
        )

        return self._dt_sensing_start

    @property
    def ds_sensing_start(self) -> datetime:
        """S2 Datastrip sensing start

        Returns:
            datetime: Datastrip sensing start
        """
        if self._ds_sensing_start:
            return self._ds_sensing_start

        self._ds_sensing_start = datetime.strptime(
            self.mtl.ds_sensing_start,
            DATE_WITH_MILLI_FORMAT
        )

        return self._ds_sensing_start

class PrismaProduct(Sentinel2Product):
    sensor = 'Prisma'
    geometry_correction_strategy = "polynomial"

    @staticmethod
    def can_handle(product_name):
        return os.path.basename(product_name).startswith('S2P')

    def get_smac_filename(self, band):
        # select S2A
        return 'Coef_{}_CONT_{}.dat'.format("S2A", band.replace('0', '').replace('8A', '8a'))
