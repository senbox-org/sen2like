import logging

import numpy as np

logger = logging.getLogger("Sen2Like")


class BaseReader:

    def __init__(self, product_path):
        self.product_path = product_path
        logger.info("%s Class" % self.__class__.__name__)
        logger.info("Product: %s" % self.product_path)
        self.scene_boundary_lon = None
        self.scene_boundary_lat = None

    def get_scene_center_coordinates(self):
        lon = np.divide(np.sum(np.double(self.scene_boundary_lon)), 4)
        lat = np.divide(np.sum(np.double(self.scene_boundary_lat)), 4)
        return lon, lat

    @staticmethod
    def can_read(product_name):
        """
        Indicates if the given product can be read by the current reader.

        :param product_name: The product to test
        :return:
        """
        return False
