# -*- coding: utf-8 -*-
# Copyright (c) 2023 ESA.
#
# This file is part of Prisma4sen2like.
# See https://github.com/senbox-org/sen2like/prisma4sen2like for further info.
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
"""Prisma L1H Preprocess entry point"""
import logging
import os
import sys
import time
from argparse import ArgumentDefaultsHelpFormatter, ArgumentParser, ArgumentTypeError

from adapter import ProductAdapter
from log import configure_logging
from prisma_product import PrismaProduct
from prisma_s2_spectral_aggregation import SpectralAggregation
from product_builder import Sen2LikeProductBuilder
from sen2like_product import Sen2LikeProduct
from version import __version__ as version

logger = logging.getLogger(__name__)


############################################################
# Arg parse config


def _validate_file(file_path):
    if not os.path.exists(file_path):
        # Argparse uses the ArgumentTypeError to give a rejection message like:
        # error: argument input: x does not exist
        raise ArgumentTypeError(f"{file_path} does not exist")

    if not os.path.isfile(file_path):
        raise ArgumentTypeError(f"{file_path} is not a file")

    return file_path


def _validate_folder(folder_path):
    if not os.path.exists(folder_path):
        # Argparse uses the ArgumentTypeError to give a rejection message like:
        # error: argument input: x does not exist
        raise ArgumentTypeError(f"{folder_path} does not exist")

    if not os.path.isdir(folder_path):
        raise ArgumentTypeError(f"{folder_path} is not a directory")

    return folder_path


_arg_parser = ArgumentParser(formatter_class=ArgumentDefaultsHelpFormatter)
_arg_parser.add_argument(
    dest="product_file_path", type=_validate_file, help="Prisma L1 he5 file", metavar="PRISMA_L1_FILE"
)
_arg_parser.add_argument(
    dest="destination_dir", type=_validate_folder, help="Generated S2P destination folder", metavar="DESTINATION_FOLDER"
)
_arg_parser.add_argument(dest="working_dir", type=_validate_folder, help="Working directory", metavar="WORKING_DIR")


############################################################
# Main


def main(argv: list[str]):
    """Program entry points

    Args:
        argv (list[str]): program arguments
    """
    args = _arg_parser.parse_args(argv)

    configure_logging(False, False)

    logger.info("Start P4S2L %s with Python %s", version, sys.version)
    # create workdir
    working_dir = os.path.join(args.working_dir, str(round(time.time() * 1000)))
    os.mkdir(working_dir)
    logger.info("Working dir: %s", working_dir)

    # configure input product, adapter, sen2like product and builder
    product = PrismaProduct(args.product_file_path)
    spectral_aggregation = SpectralAggregation(product, working_dir)
    rad, ref = spectral_aggregation.process()
    adapter = ProductAdapter(product, working_dir, 60.0)
    product.raster = ref
    product.sun_earth_correction = spectral_aggregation.sun_earth_correction

    spectral_aggregation.sun_earth_distance
    sen2like_product = Sen2LikeProduct(adapter)
    builder = Sen2LikeProductBuilder(sen2like_product, working_dir, args.destination_dir)
    # then build
    builder.build()


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
