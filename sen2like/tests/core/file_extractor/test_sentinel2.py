"""Sentinel 2 Reader test module
"""
import os
from core.readers.sentinel2 import Sentinel2MTL
from abstract_extractor_test import AbstractExtractorTestCase


test_folder_path = os.path.dirname(__file__)
roi_path_file = os.path.join(
    test_folder_path, 'Arles-communes-13-bouches-du-rhone.geojson')


class TestSentinel2Reader(AbstractExtractorTestCase):
    """Sentinel2MTL test class
    """

    def __init__(self, methodName="unitTest"):
        super().__init__(Sentinel2MTL, roi_path_file, 'Sentinel2', methodName)

    def test_s2_l1c(self):
        """test S2 L1C
        """
        image_masks = self._verify("31TFJ/S2A_MSIL1C_20171030T104151_N0500_R008_T31TFJ_20231014T203907.SAFE",
                     "nodata_pixel_mask_B01.tif", self._testMethodName)

        # self.assertEqual(s2_reader.mask_info.mask_size, 30140100)
        # self.assertEqual(s2_reader.mask_info.nb_valid_pixel, 1855204)
        # self.assertEqual(s2_reader.mask_info.nb_nodata_pixel, 28247958)

        # self.assertEqual(s2_reader.mask_info.get_valid_pixel_percentage(), 98.04782093521523)
        # self.assertEqual(s2_reader.mask_info.get_nodata_pixel_percentage(), 93.72217743139538)

    def test_s2_l2a(self):
        """test S2 LA2
        """
        self._verify("31TFJ/S2A_MSIL2A_20171030T104151_N9999_R008_T31TFJ_20200519T152631.SAFE",
                     "nodata_pixel_mask.tif", self._testMethodName)
