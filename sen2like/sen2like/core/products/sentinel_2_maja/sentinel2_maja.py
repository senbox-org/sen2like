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

import glob
import os
import re
from datetime import datetime

from core.products.product import DATE_WITH_MILLI_FORMAT, ProcessingContext, S2L_Product


class Sentinel2MajaProduct(S2L_Product):
    sensor = 'S2'
    supported_sensors = ('S2A', 'S2B')
    native_bands = ('B05', 'B06', 'B07', 'B08')
    brdf_coefficients = {"B02": {"s2_like_band_label": 'BLUE', "coef": [0.0774, 0.0079, 0.0372]},
                         "B03": {"s2_like_band_label": 'GREEN', "coef": [0.1306, 0.0178, 0.058]},
                         "B04": {"s2_like_band_label": 'RED', "coef": [0.169, 0.0227, 0.0574]},
                         "B08": {"s2_like_band_label": 'NIR', "coef": [0.3093, 0.033, 0.1535]},
                         "B8A": {"s2_like_band_label": 'NIR', "coef": [0.3093, 0.033, 0.1535]},
                         "B11": {"s2_like_band_label": 'SWIR1', "coef": [0.343, 0.0453, 0.1154]},
                         "B12": {"s2_like_band_label": 'SWIR2', "coef": [0.2658, 0.0387, 0.0639]}}
    s2_date_regexp = re.compile(r"SENTINEL2[AB]_(\d{8}-\d{6})-.*")
    s2_processing_level_regexp = re.compile(r"SENTINEL2[AB]_\d{8}-\d{6}-\d+_(.*)_.*_.+_.*")
    # override S2L_Product
    apply_sbaf_param = False

    def __init__(self, path, context: ProcessingContext):
        super().__init__(path, context)
        self.read_metadata()
        self._dt_sensing_start = None
        self._ds_sensing_start = None

    @classmethod
    def date_format(cls, name):
        regexp = cls.s2_date_regexp
        date_format = "%Y%m%d-%H%M%S"
        return regexp, date_format

    @classmethod
    def processing_level(cls, name):
        return 'LEVEL2A'

    def band_files(self, band):
        if band != 'B10':
            band = band.replace('0', '')
        return glob.glob(os.path.join(self.path, f'*_FRE_{band}.tif'))

    @property
    def sensor_name(self):
        return 'S' + self.mtl.mission[-2:]  # S2A or S2B

    @staticmethod
    def can_handle(product_name):
        return os.path.basename(product_name).startswith('SENTINEL2A_') or os.path.basename(product_name).startswith(
            'SENTINEL2B_')

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
