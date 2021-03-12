import glob
import os
import re

from core.products.product import S2L_Product


class Sentinel2Product(S2L_Product):
    sensor = 'S2'
    supported_sensors = ['S2A', 'S2B']
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

    def __init__(self, path):
        super().__init__(path)
        self.read_metadata()

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
            resolutions = sorted([resolution_dir.name for resolution_dir in os.scandir(band_path)])
            for resolution in resolutions:
                files = glob.glob(
                    os.path.join(band_path, resolution, f'*_{band}_{resolution[1:-1]}m{self.mtl.file_extension}'))
                if files:
                    return files
        return glob.glob(os.path.join(band_path, f'*_{band}{self.mtl.file_extension}'))

    def get_smac_filename(self, band):
        # select S2A or S2B coef
        name = 'S' + self.mtl.mission[-2:]  # S2A or S2B
        return 'Coef_{}_CONT_{}.dat'.format(name, band.replace('0', '').replace('8A', '8a'))

    @property
    def sensor_name(self):
        return 'S' + self.mtl.mission[-2:]  # S2A or S2B

    @staticmethod
    def can_handle(product_name):
        return os.path.basename(product_name).startswith('S2')
