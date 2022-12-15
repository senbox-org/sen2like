"""Sentinel 2 Maja Reader test module
"""
import os
from core.readers.sentinel2_maja import Sentinel2MajaMTL
from abstract_extractor_test import AbstractExtractorTestCase


test_folder_path = os.path.dirname(__file__)
roi_path_file = os.path.join(
    test_folder_path, 'Avignon-communes-84-vaucluse.geojson')


class TestSentinel2MajaReader(AbstractExtractorTestCase):
    """Sentinel2MajaMTL test class
    """

    def __init__(self, methodName="unitTest"):
        super().__init__(Sentinel2MajaMTL, roi_path_file, 'L2A_MAJA', methodName)

    def test_sentinel2_maja(self):
        """test
        """
        self._verify("SENTINEL2A_20220815-104902-689_L2A_T31TFJ_C_V3-0",
                     "nodata_pixel_mask.tif", self._testMethodName)
