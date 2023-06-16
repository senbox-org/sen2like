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

from core.products.product import ProcessingContext, S2L_Product


class Landsat8MajaProduct(S2L_Product):
    sensor = 'L8/L9'
    sensor_names = {'L8': 'LS8',
                    'L9': 'LS9'}
    supported_sensors = ('LS8', 'LS9')
    wavelength = {"B01": '440', "B02": '490', "B03": '560', "B04": '660', "B05": '860', "B06": '1630',
                  "B07": '2250', "B08": 'PAN'}
    native_bands = ('B08', 'B10', 'B11')
    brdf_coefficients = {"B02": {"s2_like_band_label": 'BLUE', "coef": [0.0774, 0.0079, 0.0372]},
                         "B03": {"s2_like_band_label": 'GREEN', "coef": [0.1306, 0.0178, 0.058]},
                         "B04": {"s2_like_band_label": 'RED', "coef": [0.169, 0.0227, 0.0574]},
                         "B05": {"s2_like_band_label": 'NIR', "coef": [0.3093, 0.033, 0.1535]},
                         "B06": {"s2_like_band_label": 'SWIR1', "coef": [0.343, 0.0453, 0.1154]},
                         "B07": {"s2_like_band_label": 'SWIR2', "coef": [0.2658, 0.0387, 0.0639]}}

    l8_date_regexp = re.compile(r"LANDSAT[89]-.*_(\d{8}-\d{6})-.*")

    def __init__(self, path, context: ProcessingContext):
        super().__init__(path, context)
        self.read_metadata()
        self.sensor = f'L{self.mtl.mission[-1]}'

    @classmethod
    def date_format(cls, name):
        regexp = cls.l8_date_regexp
        date_format = "%Y%m%d-%H%M%S"
        return regexp, date_format

    def band_files(self, band):
        if band != 'B10':
            band = band.replace('0', '')
        return glob.glob(os.path.join(self.path, f'*_FRE_{band}.tif'))

    @classmethod
    def can_handle(cls, product_name):
        return os.path.basename(product_name).startswith('LANDSAT8') or \
               os.path.basename(product_name).startswith('LANDSAT9')

    @property
    def sensor_name(self):
        return self.sensor_names[self.sensor]

    @property
    def dt_sensing_start(self) -> datetime:
        """S2 Datatake sensing start interpretation

        Returns:
            datetime: Datatake sensing start
        """
        return self.acqdate

    @property
    def ds_sensing_start(self) -> datetime:
        """S2 Datastrip sensing start interpretation

        Returns:
            datetime: Datastrip sensing start
        """
        return self.acqdate
