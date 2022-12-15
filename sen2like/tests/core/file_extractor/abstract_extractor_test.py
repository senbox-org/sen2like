"""abstract reader test module
"""
import os
import pathlib
import shutil
import filecmp

from unittest import TestCase

from core.S2L_config import config
from core.file_extractor.file_extractor import extractor_class, ImageMasks

test_folder_path = os.path.dirname(__file__)
configuration_file = os.path.join(test_folder_path, 'config.ini')


class AbstractExtractorTestCase(TestCase):
    """Base TestCase class for FileExtrator test
    """

    def __init__(self, reader_class, roi_path_file, dataset, methodName):
        """Init instance
        load a Config with config file at same file level

        Args:
            reader_class (): 'Reader' concrete class to test
            roi_path_file (_type_): roi path file for roi based tests
            dataset (_type_): Dataset path to retrieve test data, relative to base_url config param
            methodName (_type_): Method name (TestCase constructor param)

        Raises:
            Exception: if config cannot be loaded
        """
        super().__init__(methodName)
        self._reader_class = reader_class
        self.roi_path_file = roi_path_file
        if not config.initialize(configuration_file):
            raise Exception
        self._product_path = os.path.join(config.get('base_url'), dataset)

    def setUp(self):
        config.set('tile', '31TFJ')

    def tearDown(self):
        test_dir = pathlib.Path(os.path.join(
            test_folder_path, self._testMethodName))
        shutil.rmtree(test_dir)
        print("End of %s", self._testMethodName)

    def _verify(self, product_path: str, expected_no_data_file_name: str, test_method_name: str) -> ImageMasks:
        """Read given product and do some verification

        Args:
            product_path (str): Product to load and read
            expected_no_data_file_name (str): expected name of the no data file
            test_method_name (str): test method name to generated result folder and retrieve ref data

        Returns:
            BaseReader: concrete BaseReader instantiated by the function
        """
        # init reader
        s2_reader = self._reader_class(
            os.path.join(self._product_path, product_path))

        mask_filename = os.path.join(
            test_folder_path, test_method_name, f"{test_method_name}.tif")

        image_masks = extractor_class.get(s2_reader.__class__.__name__)(s2_reader).get_valid_pixel_mask(mask_filename, self.roi_path_file)

        # get masks
        # s2_reader.get_valid_pixel_mask(os.path.join(
        #     test_folder_path, test_method_name, f"{test_method_name}.tif"))

        # verify nodata mask
        nodata_mask_path = os.path.join(
            test_folder_path, test_method_name, expected_no_data_file_name)
        nodata_mask_ref_path = os.path.join(
            test_folder_path, "ref_data", test_method_name, expected_no_data_file_name)
        self._compare(nodata_mask_path, nodata_mask_ref_path)

        # verify validity mask
        validity_mask_path = os.path.join(
            test_folder_path, test_method_name, f"{test_method_name}.tif")
        validity_mask_ref_path = os.path.join(
            test_folder_path, "ref_data", test_method_name, f"{test_method_name}.tif")
        self._compare(validity_mask_path, validity_mask_ref_path)

        # FOR COVERAGE ONLY
        angle_file = os.path.join(
            test_folder_path, test_method_name, f"{test_method_name}_tie_points.tif")
        extractor_class.get(s2_reader.__class__.__name__)(s2_reader).get_angle_images(angle_file)

        return image_masks

    def _compare(self, file_path: str, ref_file_path: str):
        """Compare the 2 given files

        Args:
            file_path (str): file to verify
            ref_file_path (str): reference file
        """
        self.assertTrue(
            os.path.exists(file_path),
            msg=f"File '{file_path}' does not exists",
        )
        # same?
        self.assertTrue(
            filecmp.cmp(file_path, ref_file_path, shallow=False),
            msg=f"File differs : \n'{file_path}'\n'{ref_file_path}'",
        )
        filecmp.clear_cache()
