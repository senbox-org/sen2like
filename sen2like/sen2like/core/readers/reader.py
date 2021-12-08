import logging

import numpy as np
from abc import ABC, abstractmethod

logger = logging.getLogger("Sen2Like")


class BaseReader(ABC):

    def __init__(self, product_path):
        self.product_path = product_path
        logger.info("%s Class" % self.__class__.__name__)
        logger.info("Product: %s" % self.product_path)
        self.is_refined = False

        # Mandatory attributes
        # Need to be defined by child class
        self.product_name = None
        self.scene_boundary_lat = None
        self.scene_boundary_lon = None
        self.absolute_orbit = 'N/A'
        self.sensor = None  # Instrument
        self.angles_file = None  # All angles images
        self.data_type = None  # Product level
        self.mask_filename = None  # Mask filename
        self.observation_date = None
        self.doy = 0
        self.sun_zenith_angle = None
        self.mission = None  # Mission name
        self.cloud_cover = None
        self.relative_orbit = None
        self.nodata_mask_filename = None
        self.sun_azimuth_angle = None
        self.mtl_file_name = None
        self.file_date = None # Product date
        self.tile_metadata = None
        self.scene_center_time = None

    def get_scene_center_coordinates(self):
        lon = np.divide(np.sum(np.double(self.scene_boundary_lon)), 4)
        lat = np.divide(np.sum(np.double(self.scene_boundary_lat)), 4)
        return lon, lat

    @staticmethod
    @abstractmethod
    def can_read(product_name):
        """
        Indicates if the given product can be read by the current reader.

        :param product_name: The product to test
        :return:
        """
        return False

    @abstractmethod
    def get_valid_pixel_mask(self, mask_filename):
        pass

    @abstractmethod
    def get_angle_images(self, DST=None):
        """
        :param DST: Optional name of the output tif containing all angles images
        :return: set self.angles_file
        Following band order : SAT_AZ , SAT_ZENITH, SUN_AZ, SUN_ZENITH ')
        The unit is RADIANS
        """
        pass
