import os
from unittest import TestCase

from core.S2L_config import config
from core.image_file import S2L_ImageFile
from core.products.product import ProcessingContext
from core.products.sentinel_2.sentinel2 import Sentinel2Product
from core.products.landsat_8.landsat8 import Landsat8Product

from s2l_processes.S2L_InterCalibration import S2L_InterCalibration
from s2l_processes.S2L_Toa import S2L_Toa

test_folder_path = os.path.dirname(__file__)
configuration_file = os.path.join(test_folder_path, 'config.ini')


class TestS2L_InterCalibration(TestCase):

    def __init__(self, methodName):
        super().__init__(methodName)
        if not config.initialize(configuration_file):
            raise Exception

        config.set('wd', os.path.join(test_folder_path, methodName))


    def test_S2B_band01(self):
        _product_path = os.path.join(
            config.get('base_url'),
            'Sentinel2',
            '31TFJ',
            'S2B_MSIL1C_20171114T104259_N0500_R008_T31TFJ_20230822T002015.SAFE'
        )

        context = ProcessingContext(config, "31TFJ")
        product = Sentinel2Product(_product_path, context)
        product.working_dir = os.path.join(config.get("wd"), product.name)
        image = S2L_ImageFile(
            os.path.join(
                _product_path,
                "GRANULE/L1C_T31TFJ_A003609_20171114T104257/IMG_DATA/T31TFJ_20171114T104259_B01.jp2"
            )
        )

        # MUST RUN TOA before inter calibration
        block = S2L_Toa(False)
        image = block.process(product, image, "B01")

        block = S2L_InterCalibration(False)
        result_image = block.process(product, image, "B01")

        self.assertEqual(
            image.filepath,
            result_image.filepath,
            "Result image should be the same for S2B with baseline > 4"
        )

    def test_S2B_band09(self):
        _product_path = os.path.join(
            config.get('base_url'),
            'Sentinel2',
            '31TFJ',
            'S2B_MSIL1C_20171114T104259_N0500_R008_T31TFJ_20230822T002015.SAFE'
        )
        context = ProcessingContext(config, "31TFJ")
        product = Sentinel2Product(_product_path, context)
        product.working_dir = os.path.join(config.get("wd"), product.name)
        image = S2L_ImageFile(
            os.path.join(
                _product_path,
                "GRANULE/L1C_T31TFJ_A003609_20171114T104257/IMG_DATA/T31TFJ_20171114T104259_B09.jp2"
            )
        )

        # MUST RUN TOA before inter calibration
        block = S2L_Toa(False)
        image = block.process(product, image, "B09")

        block = S2L_InterCalibration(False)
        result_image = block.process(product, image, "B09")

        self.assertEqual(image.filepath, result_image.filepath, "Result image should be the same")

    def test_landsat(self):
        _product_path = os.path.join(config.get('base_url'), 'Landsat8',
                                     '196/29/LC81960292017318MTI00')
        context = ProcessingContext(config, "31TFJ")
        product = Landsat8Product(_product_path, context)
        product.working_dir = os.path.join(config.get("wd"), product.name)
        image = S2L_ImageFile(
            os.path.join(
                _product_path, "LC81960292017318MTI00_B3.TIF"))

        # MUST RUN TOA before inter calibration
        block = S2L_Toa(False)
        image = block.process(product, image, "B3")

        block = S2L_InterCalibration(False)
        result_image = block.process(product, image, "B3")

        self.assertEqual(image.filepath, result_image.filepath, "Result image should be the same")
