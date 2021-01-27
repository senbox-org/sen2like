import inspect
import logging
import sys

from core.module_loader import dynamic_loader, get_proj_dir
from core.readers.reader import BaseReader

log = logging.getLogger('Sen2Like')

READERS = {}


def is_reader(item):
    """Determines if `item` is a `reader.BaseReader`."""
    return inspect.isclass(item) and issubclass(item, BaseReader) and item.__name__ != BaseReader.__name__


def get_reader(product_path):
    """Get reader corresponding to given product.

    :param product_path: Path of the product file to read
    :return:
    """
    readers = [_reader for _reader in READERS.values() if _reader.can_read(product_path)]
    if len(readers) == 1:
        return readers[0]
    if len(readers) > 1:
        log.error('Multiple readers compatible with %s' % product_path)
    else:
        log.error("No reader compatible with %s" % product_path)


# Loads readers
for reader in dynamic_loader(get_proj_dir(__file__), 'readers', is_reader):
    READERS[reader.__name__] = reader
    setattr(sys.modules[__name__], reader.__name__, reader)
