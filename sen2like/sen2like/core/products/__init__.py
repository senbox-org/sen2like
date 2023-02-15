import csv
import inspect
import logging
from typing import Type
import os
import sys
from collections import OrderedDict

from core.module_loader import dynamic_loader, get_proj_dir


log = logging.getLogger('Sen2Like')


# S2L_Product classes dict, keys are S2L_Product class name
_PRODUCT_CLASS_DICT = {}
BANDS_MAPPING = {}


def is_product(item):
    """Determines if `item` is a `product.S2L_Product`."""
    from core.products.product import S2L_Product
    return inspect.isclass(item) and issubclass(item, S2L_Product) and item.__name__ != S2L_Product.__name__


def get_s2l_product_class_from_sensor_name(sensor):
    """Get product corresponding to given sensor name.

    :param sensor: Product sensor name
    :return:
    """
    for current_product in _PRODUCT_CLASS_DICT.values():
        if getattr(current_product, 'is_final', False) and sensor in getattr(current_product, 'supported_sensors', []):
            return current_product
    return None


def get_s2l_product_class(product_path) -> Type["S2L_Product"]:
    """Get S2L_Product children class corresponding to given product.

    :param product_path: Path of the product file to read
    :return:
    """
    products = [_product for _product in _PRODUCT_CLASS_DICT.values() if _product.can_handle(product_path)]
    if len(products) == 1:
        return products[0]
    if len(products) > 1:
        log.error('Multiple products reader compatible with %s', product_path)
    else:
        log.error("No product reader compatible with %s", product_path)
    return None


def read_mapping(product_class) -> OrderedDict:
    """Read bands mapping file for the given class."""
    directory = os.path.dirname(inspect.getfile(product_class))
    filename = os.path.join(directory, 'bands.csv')
    if not os.path.exists(filename):
        log.error("Invalid mapping filename: %s", filename)
        return {}
    with open(filename, 'rt') as fp:
        csv_reader = csv.reader(fp)
        next(csv_reader)
        mapping = OrderedDict({m[0]: m[1] for m in csv_reader})
    return mapping


# Loads product classes and fill _PRODUCT_CLASS_DICT
for _class in dynamic_loader(get_proj_dir(__file__), 'products', is_product):
    _PRODUCT_CLASS_DICT[_class.__name__] = _class
    setattr(sys.modules[__name__], _class.__name__, _class)

