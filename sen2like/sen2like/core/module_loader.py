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

"""This module contains functions for dynamic search and load of modules.
It helps defining modules as plugins."""

import inspect
import sys
from importlib import import_module
from os import walk
from os.path import abspath, basename, dirname, join


def get_modules(proj_dir, module):
    """Return all .py modules in given file_dir that are not __init__."""
    file_dir = abspath(join(proj_dir, module))
    for root, __, files in walk(file_dir):
        mod_path = '{}{}'.format(basename(proj_dir), root.split(proj_dir)[1]).replace('/', '.').replace('\\', '.')
        for filename in files:
            if filename.endswith('.py') and not filename.startswith('__init__'):
                yield '.'.join([mod_path, filename[0:-3]])


def dynamic_loader(proj_dir, module, compare_method):
    """Iterate over all .py files in `module` directory, finding all classes that
    match `compare` function.
    Other classes/objects in the module directory will be ignored.

    Return unique items found.
    """
    items = set()
    for mod in get_modules(proj_dir, module):
        module = import_module(mod)
        cls = inspect.getmembers(sys.modules[module.__name__], compare_method)
        items.update({cl[1] for cl in cls})
    return items


def get_proj_dir(filename):
    """Return project base directory."""
    return abspath(join(dirname(abspath(filename)), '..'))
