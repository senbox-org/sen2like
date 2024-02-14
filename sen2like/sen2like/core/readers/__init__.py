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
        log.error('Multiple readers compatible with %s', product_path)
    else:
        log.error("No reader compatible with %s", product_path)
    return None


# Loads readers
for reader in dynamic_loader(get_proj_dir(__file__), 'readers', is_reader):
    READERS[reader.__name__] = reader
    setattr(sys.modules[__name__], reader.__name__, reader)
