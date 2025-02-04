# Copyright (c) 2023 ESA.
#
# This file is part of sen2like.
# See https://github.com/senbox-org/sen2like for further info.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Base S2L Product module"""
import datetime
import logging
import os

import numpy as np
from skimage.transform import resize as skit_resize

from core import readers
from core.file_extractor.file_extractor import extractor_class
from core.image_file import S2L_ImageFile
from core.mask_util import MaskInfo
from core.products import read_mapping
from core.QI_MTD.mtd import Metadata
from core.readers import BaseReader
from core.S2L_config import S2L_Config
from core.toa_reflectance import convert_to_reflectance_from_reflectance_cal_product

logger = logging.getLogger('Sen2Like')

DATE_WITH_MILLI_FORMAT = "%Y-%m-%dT%H:%M:%S.%fZ"


class ProcessingContext:
    """
    Processing context class to store conf parameters
    that could need to be modified to properly process a product.
    It allows to override processing block activation flag (doStitching for example)
    that are used by `ProductProcess` to run or not a processing block.
    See `ProductProcess._init_block_list` implementation for more details.
    """
    def __init__(self, config: S2L_Config, tile: str):
        self.tile = tile

        self.doStitching = config.getboolean('doStitching') # pylint: disable=invalid-name
        self.doInterCalibration = config.getboolean('doInterCalibration') # pylint: disable=invalid-name

        self.doAtmcor = config.getboolean('doAtmcor') # pylint: disable=invalid-name
        self.use_sen2cor = config.getboolean('use_sen2cor')

        self.doTopographicCorrection = config.getboolean('doTopographicCorrection') # pylint: disable=invalid-name
        self.sen2cor_topographic_correction = config.getboolean('sen2cor_topographic_correction')

        if config.get('s2_processing_level') == 'LEVEL2A':

            if self.doAtmcor:
                logger.warning("Disable atmospheric correction (SMAC and sen2cor) because process L2A product")
                self.doAtmcor = False
                self.use_sen2cor = False
            
            if self.doInterCalibration:
                logger.warning("Disable inter calibration because process L2A product")
                self.doInterCalibration = False

        if not self.doTopographicCorrection:
            logger.warning("Disable sen2cor topographic correction because main topographic correction is disabled")
            self.sen2cor_topographic_correction = False
        elif config.get('s2_processing_level') == 'LEVEL2A': # only for log
            logger.warning("Will apply topographic correction on L2A product, please verify that the input L2A does not yet have topographic correction")

        if not config.getboolean('doFusion') and config.getboolean('doPackagerL2F'):
            logger.warning("Disable L2F packager because Fusion is disabled")
            self.doPackagerL2F = False # pylint: disable=invalid-name

        if config.getboolean('doFusion') and not config.getboolean('doPackagerL2F'):
            logger.warning("Disable Fusion because L2F Packaging is disabled")
            self.doFusion = False # pylint: disable=invalid-name


class ClassPropertyDescriptor(object):

    def __init__(self, fget):
        self.fget = fget

    def __get__(self, obj, klass=None):
        if klass is None:
            klass = type(obj)
        return self.fget.__get__(obj, klass)()


def classproperty(func):
    if not isinstance(func, (classmethod, staticmethod)):
        func = classmethod(func)

    return ClassPropertyDescriptor(func)

# FIXME : see to use ABC


class S2L_Product():
    _bands = None
    brdf_coefficients = {}
    image30m = {}
    _bands_mapping = None
    _reverse_bands_mapping = None
    native_bands = ()
    # TODO : have an enum ?
    geometry_correction_strategy = "translation"
    # shall apply sbaf or not,
    # consequences is that default slope,offset params will be set in quality report if False
    apply_sbaf_param = True
    # For S2, angle file reframing is not needed because very low resolution
    # other product (not in mgrs frame) must reframe it
    reframe_angle_file = True

    def __init__(self, path, context: ProcessingContext):
        # check if product exist
        if not os.path.isdir(path):
            raise IOError(f"{path} is not a valid directory.")

        self.context = context
        self.working_dir = None
        self.acqdate = None
        # TODO : rename attribute, could be tricky as "mtl" could be use for
        self.mtl: BaseReader = None
        self.filenames = {}
        self.path = path  # product directory
        self.name = os.path.basename(path)  # product name
        self.ndvi_filename = None
        self.fusion_auto_check_threshold_msk_file = None
        self.mask_info = None
        self.mask_filename = None
        self.nodata_mask_filename = None
        self.angles_file = None
        self.roi_filename = None
        # related product for stitching
        self.related_product = None
        # related image for a related_product (inside related_product, not for the current product)
        self.related_image = None
        self.dx = 0
        self.dy = 0
        # flag to indicate if product have been found to fusion the current product with
        # should be updated by fusion processing bloc
        # TODO : maybe have a object that get some info in proc block, a kind of ProcReport
        self.fusionable = True
        self.ref_image = None
        self.metadata = Metadata()

    @staticmethod
    def date(name, regexp, date_format):
        match = regexp.match(os.path.basename(name))
        if not match or not match.groups():
            logger.error("Cannot extract acquisition date from %s", name)
            return None
        return datetime.datetime.strptime(match.group(1), date_format)

    @classproperty
    def bands(self):
        if self._bands is None:
            self._bands = self.bands_mapping.keys()
        return self._bands

    @classproperty
    def bands_mapping(self):
        if self._bands_mapping is None:
            self.read_bands_mapping()
        return self._bands_mapping

    @classproperty
    def reverse_bands_mapping(self):
        if self._reverse_bands_mapping is None:
            self._reverse_bands_mapping = {v: k for k, v in self.bands_mapping.items()}
        return self._reverse_bands_mapping

    @property
    def mgrs(self) -> str:
        """
        Returns:
            str: product mgrs tile code
        """
        return self.mtl.mgrs

    def read_metadata(self):
        """Extract metadata from input product reader.
        """
        # instantiate the reader
        reader_class = readers.get_reader(self.path)
        if reader_class is None:
            return
        self.mtl = reader_class(self.path)

        # retrieve acquisition date in a datetime format
        scene_center_time = self.mtl.scene_center_time
        n = len(self.mtl.scene_center_time.split('.')[-1]) - 1  # do not count Z
        if n < 6:
            # fill with zeros
            scene_center_time = self.mtl.scene_center_time.replace('Z', (6 - n) * '0' + 'Z')
        self.acqdate = datetime.datetime.strptime(self.mtl.observation_date + ' ' + scene_center_time,
                                                  "%Y-%m-%d %H:%M:%S.%fZ")

        # TODO : understand and comment this
        if '.' in self.mtl.file_date:
            self.file_date = datetime.datetime.strptime(self.mtl.file_date, DATE_WITH_MILLI_FORMAT)
        else:
            self.file_date = datetime.datetime.strptime(self.mtl.file_date, "%Y-%m-%dT%H:%M:%SZ")

        logger.debug("Product generation time: %s", self.file_date)
        logger.debug("Acquisition Date: %s", self.acqdate)

    def get_band_filepath(self, band):
        """
        Quick access to band file path
        :param band: band
        :return: band file path
        """

        # check if already known
        if band in self.filenames:
            return self.filenames[band]

        files = self.band_files(band)
        if len(files) > 0:
            return files[-1]
        logger.warning("Product for %s band %s not found in %s", self.sensor, band, self.path)
        return None

    @classmethod
    def processing_level(cls, name):
        # pylint:disable=unused-argument
        # because need name for children classes
        return None

    def get_band_file(self, band: str) -> S2L_ImageFile:
        """Get the image band file as S2L_ImageFile.
        Also Set the product band file path in filenames[band]

        Args:
            band (str): name of the band

        Returns:
            S2L_ImageFile: the product band image, None if the band is not found
        """
        # check if not already known
        if band not in self.filenames:
            filepath = self.get_band_filepath(band)
            if filepath is None:
                return None
            # save in class internal dictionary
            self.filenames[band] = filepath
        return S2L_ImageFile(self.filenames[band])

    def band_files(self, index):
        return []

    def get_smac_filename(self, band_index):
        return ""

    @staticmethod
    def can_handle(product_path):
        return False

    @staticmethod
    def best_product(products: list[str]) -> list[str]:
        """Implementation may select and return best product

        Args:
            products (List[str]): product names

        Returns:
            (List[str]): selected products, return input product list by default
        """
        return products

    @classmethod
    def read_bands_mapping(cls):
        logger.debug("Reading bands mapping for %s", cls.__name__)
        cls._bands_mapping = read_mapping(cls)

    @classmethod
    def get_s2like_band(cls, product_band: str) -> str:
        """Get the band corresponding to s2_band for current product.

        :rtype: str
        :param product_band: The band to map to a Sentinel-2 band
        """
        return cls.bands_mapping.get(product_band)

    @classmethod
    def get_band_from_s2(cls, s2_band: str) -> str:
        return cls.reverse_bands_mapping.get(s2_band)

    def get_ndvi_image(self, ndvi_filepath):
        logger.info("Extract NDVI to %s", ndvi_filepath)
        B04_image = self.get_band_file(self.reverse_bands_mapping['B04'])
        B8A_image = self.get_band_file(self.reverse_bands_mapping['B8A'])
        B04 = B04_image.array
        B8A = B8A_image.array

        if B04_image.xRes != B8A_image.xRes:
            # up scaling  of coarser matrix to finer:
            print('band with resolution difference')
            B8A = skit_resize(B8A, B04.shape, order=3, preserve_range=True)

        # NDVI toujours basé sur les valeurs de reflectance
        B04_index = list(self.bands).index(self.reverse_bands_mapping['B04'])
        B8A_index = list(self.bands).index(self.reverse_bands_mapping['B8A'])
        B04 = convert_to_reflectance_from_reflectance_cal_product(self.mtl, B04, self.reverse_bands_mapping['B04'])
        B8A = convert_to_reflectance_from_reflectance_cal_product(self.mtl, B8A, self.reverse_bands_mapping['B8A'])
        ndvi_arr = (B8A - B04) / (B04 + B8A)
        ndvi_arr = ndvi_arr.clip(min=-1.0, max=1.0)
        np.nan_to_num(ndvi_arr, copy=False)
        ndvi = B04_image.duplicate(array=ndvi_arr, filepath=ndvi_filepath)
        self.ndvi_filename = ndvi.filepath
        ndvi.write(DCmode=True, creation_options=['COMPRESS=LZW'])
        return True

    def get_valid_pixel_mask(self, mask_filename: str, roi_file_path: str) -> bool:
        """Get validity and nodata masks from S2L Product.
        Masks are generated in the dir of 'mask_filename'.
        Mask information are computed for QI report needs
        Set in the product:
            - 'mask_filename'
            - 'nodata_mask_filename'
            - 'mask_info'
            - 'roi_filename' if roi_file_path

        Args:
            mask_filename (str): Validity mask file destination path
            roi_file_path (str): Path to roi file to apply to the mask for ROI based mode.
            Must be geojson with Polygon. Can be None if no ROI to apply.

        Returns:
            bool: if masks are valid, meaning extraction is successful
        """

        if roi_file_path:
            if not os.path.isfile(roi_file_path):
                raise AssertionError(f"roi_file_path param is not a file: {roi_file_path}")

            self.roi_filename = roi_file_path

        image_masks = extractor_class.get(
            self.mtl.__class__.__name__)(
            self.mtl).get_valid_pixel_mask(
            mask_filename, roi_file_path)

        if not image_masks:
            return False

        self.mask_filename = image_masks.validity_mask.mask_filename
        self.nodata_mask_filename = image_masks.no_data_mask.mask_filename

        # compute MaskInfo
        validity_mask = image_masks.validity_mask.mask_array
        no_data_mask = image_masks.no_data_mask.mask_array

        self.mask_info = MaskInfo(
            validity_mask.size,
            np.count_nonzero(validity_mask),
            no_data_mask.size - np.count_nonzero(no_data_mask))

        return True

    def get_angle_images(self, out_file: str):
        """"Extract angle image file from S2L Product from input product.
        set 'angles_file' in the product
        Args:
            out_file (str): file path to extract
        """
        self.angles_file = extractor_class.get(self.mtl.__class__.__name__)(self.mtl).get_angle_images(out_file)

    @property
    def absolute_orbit(self) -> str:
        """
        Returns:
            str: product absolute orbit
        """
        return self.mtl.absolute_orbit

    @property
    def sun_zenith_angle(self) -> float:
        return float(self.mtl.sun_zenith_angle)

    @property
    def sun_azimuth_angle(self) -> float:
        return float(self.mtl.sun_azimuth_angle)
