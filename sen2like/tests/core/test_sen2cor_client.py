import difflib
import filecmp
import os
from tempfile import TemporaryDirectory
from unittest import TestCase

from core.image_file import S2L_ImageFile
from core.products.product import ProcessingContext, S2L_Product
from core.readers.reader import BaseReader
from core.S2L_config import config
from core.sen2cor_client import sen2cor_client
from core.sen2cor_client.sen2cor_client import Sen2corClient as S2CClient


test_folder_path = os.path.dirname(__file__)
configuration_file = os.path.join(test_folder_path, "config.ini")


def show_diff(tested, reference):
    with open(tested) as file_1:
        file_1_text = file_1.readlines()

    with open(reference) as file_2:
        file_2_text = file_2.readlines()

    # Find and print the diff:
    for line in difflib.unified_diff(
        file_1_text, file_2_text, fromfile="tested", tofile="reference", lineterm=""
    ):
        print(line)


#
# /!\ override to stub pixel center
#
class Sen2corClient(S2CClient):

    def __init__(self, sen2cor_command, out_mgrs, enable_topo_corr=False):
        super().__init__(sen2cor_command, out_mgrs, enable_topo_corr)

    def _pixel_center(self, ref_band_file:S2L_ImageFile):
        return 4, 5


class DummyProduct(S2L_Product):
    """Simple S2L_Product having DummyReader"""

    sensor = "S2A"

    def __init__(self, path, context):
        super().__init__(path, context)
        self.mtl = DummyReader(path)


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

        if "LS" in path:
            self.mission = "LANDSAT_8"

    @staticmethod
    def can_read(product_name):
        return True


class TestSen2corClient(TestCase):
    """ProcessingContext module test class"""

    def __init__(self, methodName):
        super().__init__(methodName)
        if not config.initialize(configuration_file):
            raise Exception

    def test_dem_config(self):
        # simulate a product
        with TemporaryDirectory() as tem_dir:
            config.set("wd", tem_dir)  # set it for sen2cor
            os.makedirs(os.path.join(tem_dir, "sen2cor", "L1C_in"))

            product_dir = os.path.join(tem_dir, "L1C_in")
            os.mkdir(product_dir)
            processing_context = ProcessingContext(config, "31TFJ")
            product = DummyProduct(product_dir, processing_context)

            s2c = Sen2corClient("dummy_command", "31TFJ", True)
            # pylint: disable=protected-access  This what we want to test
            gipp_path = s2c._write_gipp(product)
            reference = os.path.join(test_folder_path, "sen2cor_L2A_GIPP_DEM_ON.xml")
            try:
                self.assertTrue(filecmp.cmp(reference, gipp_path), "Files does not match")
            except AssertionError:
                show_diff(gipp_path, reference)
                raise

            s2c = Sen2corClient("dummy_command", "31TFJ", False)
            # pylint: disable=protected-access  This what we want to test
            gipp_path = s2c._write_gipp(product)
            reference = os.path.join(test_folder_path, "sen2cor_L2A_GIPP_DEM_OFF.xml")
            try:
                self.assertTrue(filecmp.cmp(reference, gipp_path), "Files does not match")
            except AssertionError:
                show_diff(gipp_path, reference)
                raise

    def test_landsat_config(self):
        # simulate a product
        with TemporaryDirectory() as tem_dir:
            config.set("wd", tem_dir)  # set it for sen2cor
            os.makedirs(os.path.join(tem_dir, "sen2cor", "L1C_LS_in"))

            product_dir = os.path.join(tem_dir, "L1C_LS_in")
            os.mkdir(product_dir)
            processing_context = ProcessingContext(config, "31TFJ")
            product = DummyProduct(product_dir, processing_context)

            s2c = Sen2corClient("dummy_command", "31TFJ", True)
            # pylint: disable=protected-access  This what we want to test
            gipp_path = s2c._write_gipp(product)
            reference = os.path.join(test_folder_path, "sen2cor_L2A_GIPP_DEM_LS.xml")
            try:
                self.assertTrue(filecmp.cmp(reference, gipp_path), "Files does not match")
            except AssertionError:
                show_diff(gipp_path, reference)
                raise
