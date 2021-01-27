import datetime as dt
import logging
import os
import glob

from core.image_file import S2L_ImageFile
from core.products import get_product_from_sensor_name, get_product
from core.products.product import S2L_Product

logger = logging.getLogger('Sen2Like')


class S2L_HLS_Product(S2L_Product):
    # TODO: move to bands declaration
    resols_plus = [60, 10, 10, 10, 20, 20, 20, 10, 20, 20, 20]

    def __init__(self, path):
        super().__init__(path)

        # S2L_31TFJ_20171224_S2/
        try:
            self.type, self.tilecode, self.datestr, self.sensor, self.relative_orbit = self.name.split('_')
        except ValueError:
            logger.info("Cannot parse as old format %s: invalid filename" % self.name)
            self.product = None
        else:
            self.acqdate = dt.datetime.strptime(self.datestr, '%Y%m%d')
            self.product = get_product_from_sensor_name(self.sensor)
            if self.product is None:
                logger.warning("Cannot determine Product associated to sensor {}".format(self.sensor))

        if self.product is None:
            logger.info('Trying to parse S2like structure')
            try:
                # S2A_MSIL2F_20170103T104432_N9999_R008_T31TFJ_20170103T104428.SAFE
                self.sensor, self.type, self.datestr, self.pdgs, self.relative_orbit, self.tilecode, self.filedate = \
                os.path.splitext(self.name)[0].split('_')
            except ValueError:
                logger.error("Error while trying to parse %s: invalid filename" % self.name)
                self.product = None
            else:
                self.acqdate = dt.datetime.strptime(self.datestr, '%Y%m%dT%H%M%S')
                self.product = get_product_from_sensor_name('S2A')
                if self.product is None:
                    logger.error("Cannot determine Product associated to sensor {}".format(self.sensor))

    def get_band_file(self, band, plus=False):
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

        # filename
        filename = '{}_{}_{}m.TIF'.format(self.name, band, int(res))
        filepath = os.path.join(self.path, filename)
        if not os.path.exists(filepath):
            # New format
            filename = glob.glob(os.path.join(self.path, 'GRANULE', '*', 'IMG_DATA', '*{}_{}m.TIF'.format(band, int(res)))) + \
                       glob.glob(os.path.join(self.path, 'GRANULE', '*', 'IMG_DATA', 'NATIVE', '*{}_{}m.TIF'.format(band, int(res))))
            filepath = '' if not len(filename)!=0 else filename[0]
            if not os.path.exists(filepath):
                logger.error("Error: Product band {} with res {} not found in {}".format(band, int(res), self.path))
                logger.error(filepath)
                return None
        return filepath

    def getMaskFile(self):

        # return mask as S2L_ImageFile object
        filepath = self.getMask()
        return S2L_ImageFile(filepath)

    def getMask(self):
        """
        Quick access to band file path
        :return: band file path
        """

        # filename
        filename = '{}_MSK.TIF'.format(self.name)
        filepath = os.path.join(self.path, filename)
        if not os.path.exists(filepath):
            logger.warning("Product mask not found at {}".format(filepath))
            # Trying to parse with new format
            logger.info("Searching it with S2Like format")
            filename = glob.glob(os.path.join(self.path, 'GRANULE', '*', 'QI_DATA', '*_MSK.TIF'))
            filepath = '' if not len(filename) != 0 else filename[0]

            if not os.path.exists(filepath):
                logger.error("Error: Product mask not found at {}".format(os.path.join(self.path, 'GRANULE', '*', 'QI_DATA', '*_MSK.TIF')))
                return None
            else:
                logger.info("Product mask finally found")
        return filepath

    @property
    def bands(self):
        return self.product.bands
