"""Nbar tests module"""
import os
from datetime import datetime
from tempfile import TemporaryDirectory
from unittest import TestCase

from core.S2L_config import config
from core.products.product import ProcessingContext, S2L_Product
from core.readers.reader import BaseReader
from s2l_processes.S2L_Nbar import VJBMatriceBRDFCoefficient


test_folder_path = os.path.dirname(__file__)
configuration_file = os.path.join(test_folder_path, "config.ini")
aux_data_dir = os.path.join(test_folder_path, "nbar_aux_data")


class DummyProduct(S2L_Product):
    """Simple S2L_Product having DummyReader"""

    sensor = "S2A"

    def __init__(self, path, context):
        super().__init__(path, context)
        self.mtl = DummyReader(path)
        self.acqdate = datetime.strptime("2017-11-14 10:42:59.000Z","%Y-%m-%d %H:%M:%S.%fZ") 


class DummyReader(BaseReader):
    """Simple Reader impl to configure some properties used during processing"""

    def __init__(self, path):
        super().__init__(path)
        self.cloud_cover = "0.0"
        self.processing_sw = None
        if "L1C" in path:
            self.data_type = "LEVEL1C"
        else:
            self.data_type = "L2A"
        self.mgrs = "31TFJ"

    @staticmethod
    def can_read(product_name):
        return True


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
            test_folder_path,
            "data",
            "S2B_MSIL1C_20171114T104259_N0500_R008_T31TFJ_20230822T002015.SAFE"
        )
        context = ProcessingContext(config, "31TFJ")
        # product = Sentinel2Product(_product_path, context)

        with TemporaryDirectory() as tem_dir:
            
            # simulate a product
            product_dir = os.path.join(tem_dir, "L1C_in")
            os.mkdir(product_dir)

            product = DummyProduct(product_dir, context)
            # deliberately set false aux data folder (test_folder_path)
            # to not have error during object init
            vjb = VJBMatriceBRDFCoefficient(product, test_folder_path, False)

            # pylint: disable=protected-access
            assert vjb._select_vr_file(aux_data_dir) == os.path.join(
                aux_data_dir,
                "S2__USER_AUX_HABA___UV___20221028T000101_V20170105T103429_20171231T103339_T31TFJ_MLSS2_MO.nc",
            )
