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

import core.product_archive.tile_db as tile_db
from core.products.product import ProcessingContext, S2L_Product


class Landsat8Product(S2L_Product):
    sensor = 'L8/L9'
    sensor_names = {'L8': 'LS8',
                    'L9': 'LS9'}
    supported_sensors = ('LS8', 'LS9')
    is_final = True  # Indicates if this reader is a final format
    wavelength = {"B01": '440', "B02": '490', "B03": '560', "B04": '660', "B05": '860', "B06": '1630',
                  "B07": '2250', "B08": 'PAN'}
    native_bands = ('B08', 'B10', 'B11')
    brdf_coefficients = {"B02": {"s2_like_band_label": 'BLUE', "coef": [0.0774, 0.0079, 0.0372]},
                         "B03": {"s2_like_band_label": 'GREEN', "coef": [0.1306, 0.0178, 0.058]},
                         "B04": {"s2_like_band_label": 'RED', "coef": [0.169, 0.0227, 0.0574]},
                         "B05": {"s2_like_band_label": 'NIR', "coef": [0.3093, 0.033, 0.1535]},
                         "B06": {"s2_like_band_label": 'SWIR1', "coef": [0.343, 0.0453, 0.1154]},
                         "B07": {"s2_like_band_label": 'SWIR2', "coef": [0.2658, 0.0387, 0.0639]}}
    l8_date_regexp = re.compile(r"L[CTOEM]0[8-9]_.{4}_\d+_(\d+)_.*")
    l8_date_regexp_old_format = re.compile(r"L[CTOEM][8-9]\d{6}(\d{7}).*")
    l8_date_regexp_sc_format = re.compile(r"L[CTOEM]0[8-9]\d{6}(\d{8}).*")

    def __init__(self, path, context: ProcessingContext):
        super().__init__(path, context)
        self.read_metadata()
        self.sensor = f'L{self.mtl.mission.split("_")[-1]}'
        self._mgrs = None

    @classmethod
    def date_format(cls, name):
        if len(name) == 21:
            regexp = cls.l8_date_regexp_old_format
            date_format = "%Y%j"
        elif '-SC' in name:
            regexp = cls.l8_date_regexp_sc_format
            date_format = "%Y%m%d"
        else:
            regexp = cls.l8_date_regexp
            date_format = "%Y%m%d"
        return regexp, date_format

    def band_files(self, band):
        if band != 'B10':
            band = band.replace('0', '')
        files = glob.glob(self.path + '/*_{}.TIF'.format(band))
        files += glob.glob(self.path + '/*_{}.tif'.format(band))  # collection format convention
        files += glob.glob(self.path + '/*_{}.tif'.format(band.lower()))  # ledaps format convention
        return files

    def get_smac_filename(self, band):
        name = self.mtl.mission.replace("_", "")  # LANDSAT8
        # Temporal fix for LANDSAT9: Use Landsat8 coefficients
        if 'LANDSAT9' in name:
            name = name.replace('LANDSAT9', 'LANDSAT8')
        return 'Coef_{}_{}_1.dat'.format(name, self.wavelength.get(band))

    @classmethod
    def can_handle(cls, product_name):
        basename = os.path.basename(product_name)
        date_format = cls.date_format(basename)[0]
        return date_format.match(basename)

    @staticmethod
    def best_product(products: list[str]):
        """Get best consolidated products from a list.
        RT->T1/T2."""
        suffix = [prod.split('_')[-1] if '_' in prod else None for prod in products]
        for suff in ('T2', 'T1', 'RT'):
            if suff in suffix:
                return [products[suffix.index(suff)]]
        return products

    @property
    def sensor_name(self):
        return self.sensor_names[self.sensor]

    @property
    def mgrs(self) -> str:
        """Override S2L_Product mgrs property.
        It is not retrieve from reader but construct from path/row.

        Returns:
            str: mgrs tile name
        """
        # return if _mgrs is init
        if self._mgrs:
            return self._mgrs

        # otherwise set _mgrs and return
        if self.context.tile is None:
            tiles = tile_db.wrs_to_mgrs((self.mtl.path, self.mtl.row))
            self._mgrs = tiles[0] if len(tiles) else "NO_TILE"
        else:
            self._mgrs = self.context.tile

        return self._mgrs

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
