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

import datetime as dt
import glob
import logging
import os

from core.image_file import S2L_ImageFile
from core.products import get_s2l_product_class_from_sensor_name
from core.products.product import ProcessingContext, S2L_Product

logger = logging.getLogger('Sen2Like')


class S2L_HLS_Product(S2L_Product):
    # TODO: move to bands declaration
    resols_plus = [60, 10, 10, 10, 20, 20, 20, 10, 20, 20, 20]

    def __init__(self, path, context: ProcessingContext):
        super().__init__(path, context)

        # S2L_31TFJ_20171224_S2/
        try:
            self.type, self.tilecode, self.datestr, self.sensor, self.relative_orbit = self.name.split('_')
        except ValueError:
            logger.info("Cannot parse as old format %s: invalid filename", self.name)
            self.s2l_product_class = None
        else:
            self.acqdate = dt.datetime.strptime(self.datestr, '%Y%m%d')
            self.s2l_product_class = get_s2l_product_class_from_sensor_name(self.sensor)
            if self.s2l_product_class is None:
                logger.warning("Cannot determine Product associated to sensor %s", self.sensor)

        if self.s2l_product_class is None:
            logger.info('Trying to parse S2like structure')
            try:
                # S2A_MSIL2F_20170103T104432_N9999_R008_T31TFJ_20170103T104428.SAFE
                self.sensor, self.type, self.datestr, self.pdgs, self.relative_orbit, self.tilecode, self.filedate = \
                    os.path.splitext(self.name)[0].split('_')
            except ValueError:
                logger.error("Error while trying to parse %s: invalid filename", self.name)
                self.s2l_product_class = None
            else:
                self.acqdate = dt.datetime.strptime(self.datestr, '%Y%m%dT%H%M%S')
                self.s2l_product_class = get_s2l_product_class_from_sensor_name(self.sensor)
                if self.s2l_product_class is None:
                    logger.error("Cannot determine Product associated to sensor %s", self.sensor)

    def get_band_file(self, band, plus=False) -> S2L_ImageFile|None:
        # get band
        filepath = self.get_band_filepath(band, plus)

        if filepath is not None:
            return S2L_ImageFile(filepath)

    def get_band_filepath(self, band, plus=False):
        """
        Quick access to band file path
        :param band: band
        :param plus: True if sen2like+
        :return: band file path
        """

        # band and res
        res = 30
        if plus:
            res = self.resols_plus[list(self.bands).index(band)]

        extensions = S2L_ImageFile.FILE_EXTENSIONS.values()

        for ext in extensions:
            # Old format
            filename = '{}_{}_{}m.{}'.format(self.name, band, int(res), ext)
            filepath = os.path.join(self.path, filename)
            if os.path.exists(filepath):
                return filepath

            # New format
            filename = glob.glob(os.path.join(
                self.path, 'GRANULE', '*', 'IMG_DATA', '*{}_{}m.{}'.format(band, int(res), ext)))
            filename += glob.glob(os.path.join(
                self.path, 'GRANULE', '*', 'IMG_DATA', 'NATIVE', '*{}_{}m.{}'.format(band, int(res), ext)))
            filepath = '' if not len(filename) != 0 else filename[0]
            if os.path.exists(filepath):
                return filepath
        logger.debug("Product band %s with res %s not found in %s", band, int(res), self.path)
        logger.debug(filepath)
        return None

    def getMaskFile(self):

        # return mask as S2L_ImageFile object
        filepath = self.getMask()
        return S2L_ImageFile(filepath)

    def getMask(self):
        """
        Quick access to band file path
        :return: band file path
        """
        filename = glob.glob(os.path.join(self.path, 'GRANULE', '*', 'QI_DATA', '*_MSK.TIF'))
        filepath = filename[0] if filename else ''

        if not os.path.exists(filepath):
            logger.warning("Product mask not found at %s", filepath)
            # Trying to parse with old format
            filename = '{}_MSK.TIF'.format(self.name)
            filepath = os.path.join(self.path, filename)

            if not os.path.exists(filepath):
                logger.error("Error: Product mask not found with old packager format.")
                return None

            logger.info("Product mask found with old packager format")

        return filepath

    @property
    def bands(self):
        return self.s2l_product_class.bands
