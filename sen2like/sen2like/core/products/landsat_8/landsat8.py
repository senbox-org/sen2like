import glob
import os
import re
from typing import List

from core.product_archive.product_archive import InputProductArchive
from core.products.product import S2L_Product


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

    def __init__(self, path):
        super().__init__(path)
        self.read_metadata()
        self.sensor = f'L{self.mtl.mission.split("_")[-1]}'

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

    def update_site_info(self, tile=None):
        if tile is None:
            tiles = InputProductArchive.wrs_to_mgrs((self.mtl.path, self.mtl.row))
            self.mtl.mgrs = tiles[0] if len(tiles) else "NO_TILE"
        else:
            self.mtl.mgrs = tile

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
    def best_product(products: List[str]):
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
