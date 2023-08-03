"""
Test ProcessingContext configuration depending some use cases
after the call of sen2like `pre_process_atmcor` function.
`pre_process_atmcor` reconfigure the product or sen2cor output product ProcessingContext
"""

import os
from tempfile import TemporaryDirectory
from unittest import TestCase

from core.products.product import ProcessingContext, S2L_Product
from core.readers.reader import BaseReader
from core.S2L_config import config

from sen2like import sen2like

test_folder_path = os.path.dirname(__file__)
configuration_file = os.path.join(test_folder_path, "config.ini")

tmp_dir_val = {}  # store temp dir name


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

    @staticmethod
    def can_read(product_name):
        return True


class Sen2corClientStub:  # pylint: disable=too-few-public-methods
    """Sen2corClient stub"""

    def __init__(self, sen2cor_command, out_mgrs, enable_topo_corr):
        self.sen2cor_command = sen2cor_command
        self.out_mgrs = out_mgrs

    def run(self, product):
        # pylint: disable=unused-argument,missing-function-docstring
        product_dir = os.path.join(tmp_dir_val["name"], "L2A_out")
        os.mkdir(product_dir)
        return product_dir


class DummyProduct(S2L_Product):
    """Simple S2L_Product having DummyReader"""

    sensor = "S2A"

    def __init__(self, path, context):
        super().__init__(path, context)
        self.mtl = DummyReader(path)


# replace sen2cor client with its stub
sen2like.Sen2corClient = Sen2corClientStub


class TestProcessingContext(TestCase):
    """ProcessingContext module test class"""

    def __init__(self, methodName):
        super().__init__(methodName)
        if not config.initialize(configuration_file):
            raise Exception

    def process(self, is_l2a: bool = False) -> S2L_Product:
        """run `pre_process_atmcor` until the call of `update_config`"""

        with TemporaryDirectory() as tem_dir:
            tmp_dir_val["name"] = tem_dir

            # simulate a product
            product_dir = os.path.join(tem_dir, "L2A_in" if is_l2a else "L1C_in")
            os.mkdir(product_dir)
            processing_context = ProcessingContext(config, "31TFJ")
            product = DummyProduct(product_dir, processing_context)

            # sen2like product process reconfiguration
            product = sen2like.pre_process_atmcor(product, "31TFJ")

            return product

    def test_a(self):
        """process S2 L1C"""
        config.overload(
            {
                "doAtmcor": "True",
                "doTopographicCorrection": "False",
                "use_sen2cor": "True",
                "sen2cor_topographic_correction": "True",
            }
        )
        product: S2L_Product = self.process()

        self.assertFalse(
            product.context.doTopographicCorrection,
            "TopographicCorrection proc block must be disabled",
        )
        self.assertFalse(product.context.doAtmcor, "AtmCor proc block must be disabled")
        self.assertFalse(
            product.context.sen2cor_topographic_correction,
            "sen2cor topo correction must be disabled",
        )

    def test_b(self):
        """process S2 L1C"""
        config.overload(
            {
                "doAtmcor": "True",
                "doTopographicCorrection": "True",
                "use_sen2cor": "True",
                "sen2cor_topographic_correction": "True",
            }
        )
        product: S2L_Product = self.process()

        self.assertFalse(
            product.context.doTopographicCorrection,
            "TopographicCorrection proc block must be disabled",
        )
        self.assertFalse(product.context.doAtmcor, "AtmCor proc block must be disabled")
        self.assertTrue(
            product.context.sen2cor_topographic_correction,
            "sen2cor topo correction must be enabled",
        )

    def test_c(self):
        """process S2 L1C"""
        config.overload(
            {
                "doAtmcor": "True",
                "doTopographicCorrection": "True",
                "use_sen2cor": "True",
                "sen2cor_topographic_correction": "False",
            }
        )
        product: S2L_Product = self.process()

        self.assertTrue(
            product.context.doTopographicCorrection,
            "TopographicCorrection proc block must be enabled",
        )
        self.assertFalse(product.context.doAtmcor, "AtmCor proc block must be disabled")
        self.assertFalse(
            product.context.sen2cor_topographic_correction,
            "sen2cor topo correction must be disabled",
        )

    def test_d(self):
        """process S2 L1C"""
        config.overload(
            {
                "doAtmcor": "True",
                "doTopographicCorrection": "False",
                "use_sen2cor": "False",
                "sen2cor_topographic_correction": "False",
            }
        )
        product: S2L_Product = self.process()

        self.assertFalse(
            product.context.doTopographicCorrection,
            "TopographicCorrection proc block must be disabled",
        )
        self.assertTrue(product.context.doAtmcor, "AtmCor proc block must be enabled")
        self.assertFalse(product.context.use_sen2cor, "sen2cor topo correction must be disabled")
        self.assertEqual(product.mtl.data_type, "LEVEL1C")

    def test_e(self):
        """process S2 L1C"""
        config.overload(
            {
                "doAtmcor": "True",
                "doTopographicCorrection": "True",
                "use_sen2cor": "False",
                "sen2cor_topographic_correction": "False",
            }
        )
        product: S2L_Product = self.process()

        self.assertTrue(
            product.context.doTopographicCorrection,
            "TopographicCorrection proc block must be enabled",
        )
        self.assertTrue(product.context.doAtmcor, "AtmCor proc block must be enabled")
        self.assertFalse(product.context.use_sen2cor, "sen2cor topo correction must be disabled")
        self.assertEqual(product.mtl.data_type, "LEVEL1C")

    def test_f(self):
        """process S2 L2A"""
        config.overload(
            {
                "doAtmcor": "True",
                "doTopographicCorrection": "False",
                "use_sen2cor": "True",
                "sen2cor_topographic_correction": "True",
            }
        )
        config.set("s2_processing_level", "LEVEL2A")  # -l2a arg

        product: S2L_Product = self.process(True)
        self.assertFalse(
            product.context.doTopographicCorrection,
            "TopographicCorrection proc block must be disabled",
        )
        self.assertFalse(product.context.doAtmcor, "AtmCor proc block must be disabled")

    def test_g(self):
        """process S2 L2A"""
        config.overload(
            {
                "doAtmcor": "False",
                "doTopographicCorrection": "False",
                "use_sen2cor": "True",
                "sen2cor_topographic_correction": "True",
            }
        )
        config.set("s2_processing_level", "LEVEL2A")  # -l2a arg

        product: S2L_Product = self.process(True)
        self.assertFalse(
            product.context.doTopographicCorrection,
            "TopographicCorrection proc block must be disabled",
        )
        self.assertFalse(product.context.doAtmcor, "AtmCor proc block must be disabled")

    def test_h(self):
        """process S2 L2A"""
        config.overload(
            {
                "doAtmcor": "True",
                "doTopographicCorrection": "True",
                "use_sen2cor": "True",
                "sen2cor_topographic_correction": "True",
                "s2_processing_level": "LEVEL2A",  # -l2a arg
            }
        )
        config.set("s2_processing_level", "LEVEL2A")  # -l2a arg

        product: S2L_Product = self.process(True)

        self.assertTrue(
            product.context.doTopographicCorrection,
            "TopographicCorrection proc block must be enabled",
        )
        self.assertFalse(product.context.doAtmcor, "AtmCor proc block must be disabled")

    def test_i(self):
        """process S2 L2A"""
        config.overload(
            {
                "doAtmcor": "True",
                "doTopographicCorrection": "False",
                "use_sen2cor": "True",
                "sen2cor_topographic_correction": "True",
                "s2_processing_level": "LEVEL2A",  # -l2a arg
            }
        )
        config.set("s2_processing_level", "LEVEL2A")  # -l2a arg

        product: S2L_Product = self.process(True)

        self.assertFalse(
            product.context.doTopographicCorrection,
            "TopographicCorrection proc block must be disabled",
        )
        self.assertFalse(product.context.doAtmcor, "AtmCor proc block must be disabled")
