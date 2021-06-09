#! /usr/bin/env python
# -*- coding: utf-8 -*-
# V. Debaecker (TPZ-F) 2018

import calendar
import datetime as dt
import glob
import logging
import os
import re
from os.path import join, basename, dirname

import numpy as np
from skimage.transform import resize as skit_resize

from core import S2L_config
from core.image_file import S2L_ImageFile
from core.products.hls_product import S2L_HLS_Product
from grids import mgrs_framing
from s2l_processes.S2L_Process import S2L_Process

log = logging.getLogger("Sen2Like")
BINDIR = dirname(os.path.abspath(__file__))

'''
-- BQA Disctionnary definition --
     Define for a maximum of four dates (d1,d2,d3,d4) ,d4 is the most recent

 1       000001 - Not Valid pixel ( bkg)
 2       000010 - Selected date (d4)
 3       000100 - Selected date (d3)
 4       001000 - Selected date (d2)
 5       010000 - Selected date (d1)
 6       000110 - Selected date (d3,d4)
 7       001010 - Selected date (d2,d4)
 8       010010 - Selected date (d1,d4)
 9       001100 - Selected date (d2,d3)
10       010100 - Selected date (d1,d3)
11       011000 - Selected date (d1,d2)
12       001110 - Selected date (d2,d3,d4)
13       010110 - Selected date (d1,d3,d4)
14       011010 - Selected date (d1,d2,d4)
15       011110 - Selected date (d1,d2,d3,d4)

'''

bqa_val_dic = {}
bqa_val_dic.update({"1": {"value": 1, "bin_sequence": 0b0000000000000001, "label": 'bkg_fill'}})
bqa_val_dic.update({"2": {"value": 2, "bin_sequence": 0b0000000000000010, "label": 'one_date_d4'}})
bqa_val_dic.update({"3": {"value": 4, "bin_sequence": 0b0000000000000100, "label": 'one_date_d3'}})
bqa_val_dic.update({"4": {"value": 8, "bin_sequence": 0b0000000000001000, "label": 'one_date_d2'}})
bqa_val_dic.update({"5": {"value": 16, "bin_sequence": 0b0000000000010000, "label": 'one_date_d1'}})
bqa_val_dic.update({"6": {"value": 6, "bin_sequence": 0b0000000000000110, "label": 'two_date_d3_d4'}})
bqa_val_dic.update({"7": {"value": 10, "bin_sequence": 0b0000000000001010, "label": 'two_date_d2_d4'}})
bqa_val_dic.update({"8": {"value": 18, "bin_sequence": 0b0000000000010010, "label": 'two_date_d1_d4'}})
bqa_val_dic.update({"9": {"value": 12, "bin_sequence": 0b0000000000001100, "label": 'two_date_d2_d3'}})
bqa_val_dic.update({"10": {"value": 20, "bin_sequence": 0b0000000000010100, "label": 'two_date_d1_d3'}})
bqa_val_dic.update({"11": {"value": 24, "bin_sequence": 0b0000000000011000, "label": 'two_date_d1_d2'}})
bqa_val_dic.update({"12": {"value": 14, "bin_sequence": 0b0000000000001110, "label": 'three date_d2_d3_d4'}})
bqa_val_dic.update({"13": {"value": 22, "bin_sequence": 0b0000000000010110, "label": 'three date_d1_d3_d4'}})
bqa_val_dic.update({"14": {"value": 26, "bin_sequence": 0b0000000000011010, "label": 'three date_d1_d2_d4'}})
bqa_val_dic.update({"15": {"value": 30, "bin_sequence": 0b0000000000011110, "label": 'four date_d1_d2_d3_d4'}})


def get_fractional_year(ad):
    nb_days = 366 if calendar.isleap(ad.year) else 365
    x_day = np.double(ad.year) + np.double(np.divide(ad.timetuple().tm_yday, np.double(nb_days)))
    return x_day


class S2L_Fusion(S2L_Process):

    def initialize(self):
        self.reference_products = []

    def preprocess(self, pd):

        # check most recent HLS S2 products available
        archive_dir = S2L_config.config.get('archive_dir')
        tsdir = join(archive_dir, pd.mtl.mgrs)

        # list products with dates
        pdlist = []
        for pdpath in sorted(glob.glob(tsdir + '/L2F_*_S2*')):
            pdname = basename(pdpath)
            date = dt.datetime.strptime(pdname.split('_')[2], '%Y%m%d').date()
            if date <= pd.acqdate.date():
                pdlist.append([date, pdpath])

        # Handle new format aswell
        for pdpath in sorted(glob.glob(tsdir + '/S2*L2F_*')):
            pdname = basename(pdpath)
            date = dt.datetime.strptime(os.path.splitext(pdname.split('_')[2])[0], '%Y%m%dT%H%M%S').date()
            if date <= pd.acqdate.date():
                pdlist.append([date, pdpath])

        # sort by date
        pdlist.sort()

        # reset ref list and keep 2 last ones
        self.reference_products = []
        nb_products = int(S2L_config.config.get('predict_nb_products', 2))
        for date, pdname in pdlist[-nb_products:]:
            product = S2L_HLS_Product(pdname)
            if product.product is not None:
                self.reference_products.append(product)

        for product in self.reference_products:
            log.info('Selected product: {}'.format(product.name))

        S2L_config.config.set('none_S2_product_for_fusion', len(self.reference_products) == 0)

    def process(self, product, image, band):
        log.info('Start')

        if not S2L_config.config.getboolean('hlsplus'):
            log.warning('Skipping Data Fusion because doPackager and doPackagerL2F options are not activated')
            log.info('End')
            return image

        # save into file before processing (old packager will need it)
        if S2L_config.config.getboolean('doPackager'):
            product.image30m[band] = image

        if band == 'B01':
            log.warning('Skipping Data Fusion for B01.')
            log.info('End')
            return image

        if len(self.reference_products) == 0:
            log.warning('Skipping Data Fusion. Reason: no S2 products available in the past')
            log.info('End')
            return image

        if not product.get_s2like_band(band):
            log.warning('Skipping Data Fusion. Reason: no S2 matching band for {}'.format(band))
            log.info('End')
            return image

        # method selection
        predict_method = S2L_config.config.get('predict_method', 'predict')
        if len(self.reference_products) == 1:
            log.warning(
                'Not enough Sentinel2 products for the predict (only one product). Using last S2 product as ref.')
            predict_method = 'composite'

        # general info
        band_s2 = product.get_s2like_band(band)
        image_file_L2F = self.reference_products[0].get_band_file(band_s2, plus=True)
        output_shape = (image_file_L2F.ySize, image_file_L2F.xSize)

        # method: prediction (from the 2 most recent S2 products)
        if predict_method == 'predict':
            # Use QA (product selection) to apply Composting :
            qa_mask = self._get_qa_band(output_shape)

            # predict
            array_L2H_predict, array_L2F_predict = self._predict(product, band_s2, qa_mask, output_shape)

            # save
            if S2L_config.config.getboolean('generate_intermediate_products'):
                self._save_as_image_file(image_file_L2F, qa_mask, product, band, '_FUSION_QA.TIF')
                self._save_as_image_file(image_file_L2F, array_L2H_predict, product, band, '_FUSION_L2H_PREDICT.TIF')
                self._save_as_image_file(image_file_L2F, array_L2F_predict, product, band, '_FUSION_L2F_PREDICT.TIF')

        # method: composite (most recent valid pixels from N products)
        elif predict_method == 'composite':
            # composite
            array_L2H_predict, array_L2F_predict = self._composite(product, band_s2, output_shape)

            # save
            if S2L_config.config.getboolean('generate_intermediate_products'):
                self._save_as_image_file(image_file_L2F, array_L2H_predict, product, band, '_FUSION_L2H_COMPO.TIF')
                self._save_as_image_file(image_file_L2F, array_L2F_predict, product, band, '_FUSION_L2F_COMPO.TIF')

        # method: unknown
        else:
            log.error(f'Unknown predict method: {predict_method}. Please check your configuration.')
            return None

        # fusion L8/S2
        mask_filename = product.mtl.nodata_mask_filename
        array_out = self._fusion(image, array_L2H_predict, array_L2F_predict, mask_filename).astype(np.float32)
        image = self._save_as_image_file(image_file_L2F, array_out, product, band, '_FUSION_L2H_PREDICT.TIF')

        log.info('End')

        return image

    def _save_as_image_file(self, image_template, array, product, band, extension):
        path = os.path.join(S2L_config.config.get('wd'), product.name, product.get_band_file(band).rootname + extension)
        image_file = image_template.duplicate(path, array=array)
        if S2L_config.config.getboolean('generate_intermediate_products'):
            image_file.write(creation_options=['COMPRESS=LZW'])
        return image_file

    def _get_qa_band(self, shape):
        # Compute number of dates
        number_of_dates = len(self.reference_products)

        # Read first image :
        # Create an empty numpy n-d array :
        msk_qa = np.zeros(shape, dtype=np.uint8)

        # Read and save in a n-d numpy array the mask for each date
        # Create QA Band as output of this processing :
        for i in range(1, number_of_dates + 1, 1):
            pd = self.reference_products[i - 1]
            mskfile = pd.getMaskFile()
            log.debug(mskfile.filepath)
            msk = mskfile.array

            if msk.shape != shape:
                msk = skit_resize(msk.clip(min=-1.0, max=1.0), shape, order=0, preserve_range=True).astype(
                    np.uint8)

            msk_qa += msk * np.power(2, i)

        return msk_qa

    def _composite(self, product, band_s2, output_shape):
        """
        Makes a composite from reference products (usually last S2 L2F/L2H products), with the most recent
        valid pixels (no predict), using validity masks.
        Returns 2 images, one high res (typically 10 or 20m), and one low resolution (typically 30m)
        resampled to high res.

        :param pd: L8 product (S2L_Product object)
        :param bandindex: band index
        :return: 2 composites (high res and low res upsampled to high res)
        """

        log.info('compositing with {} products'.format(len(self.reference_products)))

        array_L2H_compo = None
        array_L2F_compo = None

        for pd in self.reference_products:

            # image L2F
            image_file_L2F = pd.get_band_file(band_s2, plus=True)
            array_L2F = image_file_L2F.array.astype(np.float32) / 10000.

            # image L2H
            array_L2H = self.get_harmonized_product(pd, band_s2, output_shape, False)

            # resample L2H to resolution of L2F (prepraring LOWPASS):
            array_L2H = skit_resize(array_L2H.clip(min=-1.0, max=1.0), output_shape, order=1).astype(np.float32)

            # read mask :
            mskfile = pd.getMaskFile()
            msk = mskfile.array

            # resample mask if needed
            if msk.shape != array_L2F.shape:
                msk = skit_resize(msk.clip(min=-1.0, max=1.0), output_shape, order=0, preserve_range=True).astype(
                    np.uint8)

            # apply in composite
            if array_L2H_compo is None:
                array_L2H_compo = np.zeros(output_shape, np.float32)
                array_L2F_compo = np.zeros(output_shape, np.float32)
            array_L2H_compo = np.where(msk == 0, array_L2H_compo, array_L2H)
            array_L2F_compo = np.where(msk == 0, array_L2F_compo, array_L2F)

        return array_L2H_compo, array_L2F_compo

    def _predict(self, product, band_s2, qa_mask, output_shape):
        """Provide the best prediction image for a given date

        Input : Expected DOY
                S2 TDS
        """
        log.info('prediction')

        # From QA
        if output_shape != qa_mask.shape:
            log.error("Fusion qa_mask mask and output do not have the same shapes")
        M1 = np.zeros(qa_mask.shape, np.uint8)
        M2 = np.zeros(qa_mask.shape, np.uint8)
        M3 = np.zeros(qa_mask.shape, np.uint8)
        M1[qa_mask == 6] = 1
        M2[qa_mask == 4] = 1  # d3
        M3[qa_mask == 2] = 1  # d4

        # init output images
        output_images = {'L2H': None, 'L2F': None}

        # (oldest date) and (newest date)
        pd1 = self.reference_products[0]
        doy_1 = get_fractional_year(pd1.acqdate)
        log.debug('{} {}'.format(pd1.name, doy_1))
        pd2 = self.reference_products[1]
        doy_2 = get_fractional_year(pd2.acqdate)

        # doy of input product
        input_xdoy = get_fractional_year(product.acqdate)
        log.debug('input_xdoy: {}'.format(input_xdoy))

        for mode in output_images.keys():
            plus = mode == 'L2F'

            # image1 (oldest date)
            array1 = self.get_harmonized_product(pd1, band_s2, output_shape, plus)

            # image2 (newest date)
            array2 = self.get_harmonized_product(pd2, band_s2, output_shape, plus)

            # Compute
            A = (array2 - array1) / (doy_2 - doy_1)
            B = array2 - A * doy_2

            # Compute Predicted Image at input_xdoy
            array_dp_raw = A * (np.float(input_xdoy)) + B

            array_dp = array_dp_raw * M1 + array1 * M3 + array2 * M2  # + array_dp_raw [qa_mask == 0]

            output_images[mode] = array_dp

        return output_images['L2H'], output_images['L2F']

    @staticmethod
    def get_harmonized_product(product, band_s2, output_shape, plus):
        image_file = product.get_band_file(band_s2, plus=plus)

        if image_file is None:
            log.info('Resampling to 30m: Start...')
            band_file = product.get_band_file(band_s2, plus=True)
            match = re.search(r'_(\d{2})m', band_file.filename)
            if match:
                resampled_file = band_file.filename.replace(match.group(1), '30')
            else:
                resampled_file = band_file.filename.replace('.', '_resampled_30m.')
            image_file = mgrs_framing.resample(band_file, 30, os.path.join(band_file.dirpath, resampled_file))
            log.info('Resampling to 30m: End')
        array = image_file.array.astype(np.float32) / 10000.
        if output_shape != array.shape:
            array = skit_resize(array.clip(min=-1.0, max=1.0), output_shape).astype(np.float32)
        return array

    def _fusion(self, L8_HLS, S2_HLS_img, S2_HLS_plus_img, mask_filename=None):

        log.info('fusion')
        # read array
        L8_HLS_img = L8_HLS.array

        # resize low res to high res
        L8_HLS_plus_BILINEAR_img = skit_resize(L8_HLS_img.clip(min=-1.0, max=1.0), S2_HLS_plus_img.shape).astype(
            np.float32)
        S2_HLS_plus_LOWPASS_img = S2_HLS_img

        # high pass of high res
        S2_HLS_plus_HIGHPASS_img = S2_HLS_plus_img - S2_HLS_plus_LOWPASS_img

        # fusion
        L8_HLS_plus_FUSION_img = L8_HLS_plus_BILINEAR_img + S2_HLS_plus_HIGHPASS_img

        # masking
        if mask_filename:
            mask_file = S2L_ImageFile(mask_filename)
            msk = mask_file.array
            if msk.shape != L8_HLS_plus_FUSION_img.shape:
                msk = skit_resize(msk.clip(min=-1.0, max=1.0), L8_HLS_plus_FUSION_img.shape, order=0,
                                  preserve_range=True).astype(np.uint8)
            L8_HLS_plus_FUSION_img[msk == 0] = 0

        return L8_HLS_plus_FUSION_img
