import glob
import os
import re

from core.products.product import S2L_Product


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

    def __init__(self, path):
        super().__init__(path)
        self.read_metadata()

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
