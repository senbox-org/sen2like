"""Nbar tests module"""
import os
from unittest import TestCase

from core.S2L_config import config
from core.products.product import ProcessingContext
from core.products.sentinel_2.sentinel2 import Sentinel2Product
from s2l_processes.S2L_Nbar import VJBMatriceBRDFCoefficient


test_folder_path = os.path.dirname(__file__)
configuration_file = os.path.join(test_folder_path, "config.ini")
aux_data_dir = os.path.join(test_folder_path, "nbar_aux_data")


class TestS2L_Nbar(TestCase):
    """S2L_Nbar module test class"""

    def __init__(self, methodName):
        super().__init__(methodName)
        if not config.initialize(configuration_file):
            raise Exception

    def test_select_vr_file(self):
        """Test VJBMatriceBRDFCoefficient._select_vr_file
        WARN : aux_data_dir contains dummy files, only their filenames are used to verify the method result
        """
        _product_path = os.path.join(
            config.get("base_url"),
            "Sentinel2",
            "31TFJ",
            "S2B_MSIL1C_20171114T104259_N0206_R008_T31TFJ_20171114T124011.SAFE",
        )
        context = ProcessingContext(config, "31TFJ")
        product = Sentinel2Product(_product_path, context)
        # deliberately set false aux data folder (test_folder_path)
        # to not have error during object init
        vjb = VJBMatriceBRDFCoefficient(product, None, "B04", test_folder_path, False)

        # pylint: disable=protected-access
        assert vjb._select_vr_file(aux_data_dir) == os.path.join(
            aux_data_dir,
            "S2__USER_AUX_HABA___UV___20221028T000101_V20170105T103429_20171231T103339_T31TFJ_MLSS2_MO.nc",
        )
