import datetime
import datetime as dt
import logging
import os

from core import readers
from core import S2L_config
from core.image_file import S2L_ImageFile
from core.products import read_mapping

logger = logging.getLogger('Sen2Like')


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


class S2L_Product(object):
    _bands = None
    brdf_coefficients = {}
    image30m = {}
    _bands_mapping = None
    _reverse_bands_mapping = None
    native_bands = ()

    def __init__(self, path):
        # check if product exist
        if not os.path.isdir(path):
            raise IOError("%s is not a valid directory." % path)

        self.acqdate = None
        self.mtl = None
        self.filenames = {}
        self.path = path  # product directory
        self.name = os.path.basename(path)  # product name

    @staticmethod
    def date(name, regexp, date_format):
        match = regexp.match(os.path.basename(name))
        if not match or not match.groups():
            logger.error("Cannot extract acquisition date from {}".format(name))
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

    def read_metadata(self, granule_folder='GRANULE'):
        # extract metadata
        self.mtl = readers.get_reader(self.path)
        if self.mtl is None:
            return
        self.mtl = self.mtl(self.path)

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
        self.acqdate = dt.datetime.strptime(self.mtl.observation_date + ' ' + scene_center_time,
                                            "%Y-%m-%d %H:%M:%S.%fZ")

        if 'S2' in self.sensor or self.mtl.data_type in ['Level-2F', 'Level-2H']:  # Sentinel 2
            self.dt_sensing_start = dt.datetime.strptime(self.mtl.dt_sensing_start, "%Y-%m-%dT%H:%M:%S.%fZ")
            self.ds_sensing_start = dt.datetime.strptime(self.mtl.ds_sensing_start, "%Y-%m-%dT%H:%M:%S.%fZ")

            logger.debug("Datatake sensing start: {}".format(self.dt_sensing_start))
            logger.debug("Datastrip sensing start: {}".format(self.ds_sensing_start))
        if '.' in self.mtl.file_date:
            self.file_date = dt.datetime.strptime(self.mtl.file_date, "%Y-%m-%dT%H:%M:%S.%fZ")
        else:
            self.file_date = dt.datetime.strptime(self.mtl.file_date, "%Y-%m-%dT%H:%M:%SZ")

        logger.debug("Product generation time: {}".format(self.file_date))
        logger.debug("Acquisition Date: {}".format(self.acqdate))

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
        logger.warning("Product for {} band {} not found in {}".format(self.sensor, band, self.path))
        return None

    @classmethod
    def processing_level(cls, name):
        return None

    def get_band_file(self, band):
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
        logger.debug("Reading bands mapping for %s" % cls)
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
