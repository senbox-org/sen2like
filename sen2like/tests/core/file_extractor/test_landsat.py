"""Landsat Reader test module
"""
import os
from core.readers.landsat import LandsatMTL
from abstract_extractor_test import AbstractExtractorTestCase


test_folder_path = os.path.dirname(__file__)
roi_path_file = os.path.join(
    test_folder_path, 'Avignon-communes-84-vaucluse.geojson')


class TestLandsatReader(AbstractExtractorTestCase):
    """LandsatMTL test class
    """

    def __init__(self, methodName="unitTest"):
        super().__init__(LandsatMTL, roi_path_file, 'Landsat8', methodName)

    def test_landsat(self):
        """test S2 L1C
        """
        self._verify("196/29/LC81960292017318MTI00",
                     "nodata_pixel_mask.tif", self._testMethodName)
