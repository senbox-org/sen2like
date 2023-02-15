"""Base MTL/MTD reader class

Returns:
    MaskImage: dataclass having enough to write a mask file
    ImageMasks: dataclass combination of nodata et validity mask as 'MaskImage'
    MaskInfo: dataclass having enough to compute mask QI info
    BaseReader: Base class for MTL/MTD reader
"""
import logging
from abc import ABC, abstractmethod
import numpy as np


logger = logging.getLogger("Sen2Like")


def compute_scene_boundaries(scene_boundary_lat, scene_boundary_lon):
    """Compute scene boundary from list of lat and lon

    Args:
        scene_boundary_lat (list[number]): list of latitudes
        scene_boundary_lon (list[number]): list of longitudes

    Returns:
        tuple: tuple of list of lat and list of lon
    """
    arr1 = np.asarray(scene_boundary_lat, float)
    arr1_r = np.roll(arr1, -1)
    # Retour d index
    arr2 = np.asarray(scene_boundary_lon, float)
    arr2_r = np.roll(arr2, -1)
    x = arr1_r - arr1  # Vecteur X - latitude
    y = arr2_r - arr2  # Vecteur Y - longitude
    # Remove point with diff null in the two direction
    index = (np.argwhere((x == 0) & (y == 0))).flatten()
    x = np.delete(x, index)
    y = np.delete(y, index)
    x_r = np.roll(x, -1)
    y_r = np.roll(y, -1)
    scalar = np.multiply(x, x_r) + np.multiply(y, y_r)  # Scalar product
    # Norm
    norm = np.power(np.multiply(x, x) + np.multiply(y, y), 0.5)
    norm_r = np.roll(norm, -1)
    # Product of Norm || U || * || V ||

    theta = np.roll(
        np.arccos(np.divide(scalar, np.multiply(norm, norm_r))) * (np.divide(180, np.pi)),
        1)
    arr1 = np.delete(arr1, index)
    arr2 = np.delete(arr2, index)
    return (arr1[theta > 60.0].tolist(), arr2[theta > 60.0].tolist())


class BaseReader(ABC):
    """Base reader for image metadata extraction"""

    def __init__(self, product_path):
        self.product_path = product_path
        logger.info("%s Class",  self.__class__.__name__)
        logger.info("Product: %s", self.product_path)
        self.is_refined = False

        # Mandatory attributes
        # Need to be defined by child class
        self.product_name = None
        self.scene_boundary_lat = None
        self.scene_boundary_lon = None
        self.absolute_orbit = 'N/A'
        self.sensor = None  # Instrument
        self.data_type = None  # Product level
        self.observation_date = None
        self.doy = 0
        self.sun_zenith_angle = None
        self.mission = None  # Mission name
        self.cloud_cover = None
        self.relative_orbit = None
        self.sun_azimuth_angle = None
        self.mtl_file_name = None
        self.file_date = None  # Product date
        self.tile_metadata = None
        self.scene_center_time = None
        self.l2a_qi_report_path = None

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
