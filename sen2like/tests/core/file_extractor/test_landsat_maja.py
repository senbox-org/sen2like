"""Landsat Maja Reader test module
"""
import os
from core.readers.landsat_maja import LandsatMajaMTL
from abstract_extractor_test import AbstractExtractorTestCase


test_folder_path = os.path.dirname(__file__)
roi_path_file = os.path.join(
    test_folder_path, 'Avignon-communes-84-vaucluse.geojson')


class TestLandsatMajaExtractor(AbstractExtractorTestCase):
    """LandsatMajaMTL test class"""

    def __init__(self, methodName="unitTest"):
        super().__init__(LandsatMajaMTL, roi_path_file, 'L2A_MAJA', methodName)

    def test_landsat_maja(self):
        """test S2 L1C
        """
        self._verify("LANDSAT8-OLITIRS-XS_20210821-102351-515_L2A_T31TFJ_C_V2-2",
                     "nodata_pixel_mask.tif", self._testMethodName)
