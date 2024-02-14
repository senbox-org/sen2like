"""S2L processes module tests"""
import os
from unittest import TestCase

from core.S2L_config import config
from s2l_processes import create_process_block
from s2l_processes.S2L_Sbaf import S2L_Sbaf
from s2l_processes.S2L_Toa import S2L_Toa
from s2l_processes.S2L_TopographicCorrection import S2L_TopographicCorrection

test_folder_path = os.path.dirname(__file__)
configuration_file = os.path.join(test_folder_path, "config.ini")


class TestS2LProcesses(TestCase):
    def __init__(self, methodName):
        super().__init__(methodName)
        if not config.initialize(configuration_file):
            raise Exception
        config.set("generate_intermediate_products", False)

    def test_create(self):
        assert isinstance(
            create_process_block("S2L_TopographicCorrection"), S2L_TopographicCorrection
        )
        assert isinstance(create_process_block("S2L_Toa"), S2L_Toa)
        assert isinstance(create_process_block("S2L_Sbaf"), S2L_Sbaf)

        self.assertRaises(RuntimeError, create_process_block, "bad module name")
