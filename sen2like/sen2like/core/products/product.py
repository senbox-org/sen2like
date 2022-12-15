import datetime
import logging
import os
import numpy as np
from skimage.transform import resize as skit_resize

from core import readers
from core import S2L_config
from core.file_extractor.file_extractor import MaskInfo, extractor_class
from core.image_file import S2L_ImageFile
from core.products import read_mapping
from core.readers import BaseReader
from core.toa_reflectance import convert_to_reflectance_from_reflectance_cal_product

logger = logging.getLogger('Sen2Like')

DATE_WITH_MILLI_FORMAT = "%Y-%m-%dT%H:%M:%S.%fZ"


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

    def __init__(self, path):
        # check if product exist
        if not os.path.isdir(path):
            raise IOError(f"{path} is not a valid directory.")

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

    def read_metadata(self):
        # extract metadata
        reader_class = readers.get_reader(self.path)
        if reader_class is None:
            return
        # instantiate the reader
        self.mtl = reader_class(self.path)

        try:
            self.update_site_info(S2L_config.config.get('tile', None))
        except AttributeError:
            # Some products not need to update their site information
            pass

        # retrieve acquisition date in a datetime format
        scene_center_time = self.mtl.scene_center_time
        n = len(self.mtl.scene_center_time.split('.')[-1]) - 1  # do not count Z
        if n < 6:
            # fill with zeros
            scene_center_time = self.mtl.scene_center_time.replace('Z', (6 - n) * '0' + 'Z')
        self.acqdate = datetime.datetime.strptime(self.mtl.observation_date + ' ' + scene_center_time,
                                                  "%Y-%m-%d %H:%M:%S.%fZ")

        if 'S2' in self.sensor or self.mtl.data_type in ['Level-2F', 'Level-2H']:  # Sentinel 2
            self.dt_sensing_start = datetime.datetime.strptime(self.mtl.dt_sensing_start, DATE_WITH_MILLI_FORMAT)
            self.ds_sensing_start = datetime.datetime.strptime(self.mtl.ds_sensing_start, DATE_WITH_MILLI_FORMAT)

            logger.debug("Datatake sensing start: %s", self.dt_sensing_start)
            logger.debug("Datastrip sensing start: %s", self.ds_sensing_start)

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
