#! /usr/bin/env python
# -*- coding: utf-8 -*-
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

"""Fusion processing block module"""

import calendar
import datetime as dt
import glob
import logging
import os
import re
from os.path import basename, join

import numpy as np
from skimage.measure import block_reduce
from skimage.morphology import dilation, square
from skimage.transform import resize as skit_resize

from core import S2L_config
from core.image_file import S2L_ImageFile
from core.products.hls_product import S2L_HLS_Product
from core.products.product import S2L_Product
from core.S2L_tools import out_stat
from grids import mgrs_framing
from s2l_processes.S2L_Process import S2L_Process

log = logging.getLogger("Sen2Like")

'''
-- BQA Dictionary definition --
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

    def __init__(self, generate_intermediate_products: bool):
        super().__init__(generate_intermediate_products)
        self.reference_products : list(S2L_HLS_Product) = []
        self._predict_method = None

    def preprocess(self, product: S2L_Product):

        log.info('Start')

        # check most recent HLS S2 products available
        archive_dir = S2L_config.config.get('archive_dir')
        tsdir = join(archive_dir, product.mgrs)

        # list products with dates
        pdlist = []

        # Handle new format aswell
        for pdpath in sorted(glob.glob(tsdir + '/S2*L2F_*')):
            pdname = basename(pdpath)
            date = dt.datetime.strptime(
                os.path.splitext(pdname.split('_')[2])[0], '%Y%m%dT%H%M%S'
            ).date()

            if date <= product.acqdate.date():
                pdlist.append([date, pdpath])

        # sort by date
        pdlist.sort()

        # reset ref list and keep 2 last ones
        nb_products = int(S2L_config.config.get('predict_nb_products', 2))
        for date, pdname in pdlist[-nb_products:]:
            ref_product = S2L_HLS_Product(pdname, product.context)
            if ref_product.s2l_product_class is not None:
                self.reference_products.append(ref_product)

        for ref_product in self.reference_products:
            log.info('Selected product: %s', ref_product.name)

        product.fusionable = len(self.reference_products) > 0

        log.info('End')

    def process(self, product: S2L_Product, image: S2L_ImageFile, band: str) -> S2L_ImageFile:
        log.info('Start')

        if not product.fusionable:
            log.warning('Skipping Data Fusion. Reason: no S2 products available in the past')
            log.info('End')
            return image

        if band == 'B01':
            log.warning('Skipping Data Fusion for B01.')
            log.info('End')
            return image

        if not product.get_s2like_band(band):
            log.warning('Skipping Data Fusion. Reason: no S2 matching band for %s', band)
            log.info('End')
            return image

        # method selection
        predict_method = S2L_config.config.get('predict_method', 'predict')
        if len(self.reference_products) == 1:
            log.warning(
                'Not enough Sentinel2 products for the predict (only one product). Using last S2 product as ref.')
            predict_method = 'composite'

        self._predict_method = predict_method
        # general info
        band_s2 = product.get_s2like_band(band)
        image_file_L2F = self.reference_products[0].get_band_file(band_s2, plus=True)
        output_shape = (image_file_L2F.ySize, image_file_L2F.xSize)

        # method: prediction (from the 2 most recent S2 products)
        if self._predict_method == 'predict':
            # Use QA (product selection) to apply Composting :
            qa_mask = self._get_qa_band(output_shape)

            # predict
            array_L2H_predict, array_L2F_predict = self._predict(product, band_s2, qa_mask, output_shape)

            # save
            if self.generate_intermediate_products:
                self._save_as_image_file(image_file_L2F, qa_mask, product, band, '_FUSION_QA.TIF')
                self._save_as_image_file(image_file_L2F, array_L2H_predict, product, band, '_FUSION_L2H_PREDICT.TIF')
                self._save_as_image_file(image_file_L2F, array_L2F_predict, product, band, '_FUSION_L2F_PREDICT.TIF')

        # method: composite (most recent valid pixels from N products)
        elif self._predict_method == 'composite':
            # composite
            array_L2H_predict, array_L2F_predict = self._composite(band_s2, output_shape)

            # save
            if self.generate_intermediate_products:
                self._save_as_image_file(image_file_L2F, array_L2H_predict, product, band, '_FUSION_L2H_COMPO.TIF')
                self._save_as_image_file(image_file_L2F, array_L2F_predict, product, band, '_FUSION_L2F_COMPO.TIF')

        # method: unknown
        else:
            log.error('Unknown predict method: %s. Please check your configuration.', self._predict_method)
            return None

        # fusion L8/S2
        mask_filename = product.nodata_mask_filename
        array_out = self._fusion(image, array_L2H_predict, array_L2F_predict, mask_filename).astype(np.float32)
        image_out = self._save_as_image_file(image_file_L2F, array_out, product, band, '_FUSION_FINAL.TIF')

        # fusion auto check
        if band == S2L_config.config.get('fusion_auto_check_band'):
            nodata_value = 150
            proportion_diff, proportion_diff_mask = self.proportion_fusion_diff(
                image, image_out, S2L_ImageFile(mask_filename), nodata_value=nodata_value)
            log.debug('Fusion auto check proportional difference of L2F from L2H')
            out_stat(proportion_diff * proportion_diff_mask, log, 'proportional diff')
            if self.generate_intermediate_products:
                proportion_diff_img = image.duplicate(
                    filepath=os.path.join(
                        product.working_dir,
                        f'fusion_auto_check_proportion_diff_{band}.TIF'
                    ),
                    array=proportion_diff)
                proportion_diff_img.write(creation_options=['COMPRESS=LZW'], DCmode=True, nodata_value=nodata_value)

            abs_proportion_diff = np.abs(proportion_diff * proportion_diff_mask)
            threshold_msk = np.zeros(abs_proportion_diff.shape, dtype=np.uint16)
            threshold_msk[abs_proportion_diff < S2L_config.config.getfloat('fusion_auto_check_threshold')] = 1
            threshold_msk[proportion_diff_mask == 0] = 0
            threshold_msk = image.duplicate(
                filepath=os.path.join(
                    product.working_dir,
                    f'fusion_auto_check_threshold_msk_{band}.TIF'
                ),
                array=threshold_msk)
            threshold_msk.write(creation_options=['COMPRESS=LZW'])
            product.fusion_auto_check_threshold_msk_file = threshold_msk.filepath

        log.info('End')

        return image_out

    def postprocess(self, product: S2L_Product):
        """Set QI params

        Args:
            product (S2L_Product): product to post process
        """

        log.info('Start')

        product.metadata.qi["FUSION_AUTO_CHECK_THRESHOLD"] = S2L_config.config.getfloat(
            'fusion_auto_check_threshold')

        product.metadata.qi["PREDICTED_METHOD"] = self._predict_method

        log.info('End')

    def _save_as_image_file(self, image_template, array, product, band, extension):
        path = os.path.join(
            product.working_dir,
            product.get_band_file(band).rootname + extension
        )
        image_file = image_template.duplicate(path, array=array)
        if self.generate_intermediate_products:
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

    def _composite(self, band_s2, output_shape):
        """
        Makes a composite from reference products (usually last S2 L2F/L2H products), with the most recent
        valid pixels (no predict), using validity masks.
        Returns 2 images, one high res (typically 10 or 20m), and one low resolution (typically 30m)
        resampled to high res.

        :param bandindex: band index
        :return: 2 composites (high res and low res upsampled to high res)
        """

        log.info('compositing with %s products', len(self.reference_products))

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
        log.debug('%s %s', pd1.name, doy_1)
        pd2 = self.reference_products[1]
        doy_2 = get_fractional_year(pd2.acqdate)

        # doy of input product
        input_xdoy = get_fractional_year(product.acqdate)
        log.debug('input_xdoy: %s', input_xdoy)

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
            array_dp_raw = A * (float(input_xdoy)) + B

            array_dp = array_dp_raw * M1 + array1 * M3 + array2 * M2  # + array_dp_raw [qa_mask == 0]

            output_images[mode] = array_dp

        return output_images['L2H'], output_images['L2F']

    @staticmethod
    def get_harmonized_product(product, band_s2, output_shape, plus):
        # Search for S2 L2H at 30 m resolution (legacy L2H products)
        image_file = product.get_band_file(band_s2, plus=plus)

        # Initialize border to None in case S2 legacy L2H products are found (30 m resolution)
        border = None

        if image_file is None:
            log.info('Resampling to 30m: Start...')
            # Search for S2 L2H at native (full) resolution (10 m, 20 m)
            band_file = product.get_band_file(band_s2, plus=True)
            # Construct temporary nodata mask with pixels equal to 0
            nodata = (band_file.array == 0)
            # Dilate temporary nodata mask by one pixel using a square operator of size 3
            nodatadil = dilation(nodata, square(3))
            # Substract nodata mask to dilated mask to create border mask array
            # border mask array identifies the pixels defining the (internal) border of image close to the nodata area
            # border mask array is at native (full) resolution (10 m, 20 m)
            border = nodatadil ^ nodata

            match = re.search(r'_(\d{2})m', band_file.filename)
            if match:
                resampled_file = band_file.filename.replace(match.group(1), '30')
            else:
                resampled_file = band_file.filename.replace('.', '_resampled_30m.')
            # Resample S2 L2H at native (full) resolution (10 m, 20 m) to 30 m
            image_file = mgrs_framing.resample(band_file, 30, os.path.join(band_file.dirpath, resampled_file))
            log.info('Resampling to 30m: End')

        # Convert array from DN to float
        # TODO: check if radiometric offset (since S2 PB 04.00) needs to be take into account. It seems it is not mandatory
        array = image_file.array.astype(np.float32) / 10000.

        if output_shape != array.shape:
            array = skit_resize(array.clip(min=-1.0, max=1.0), output_shape).astype(np.float32)
            # Perform the reset of border values to initial L2H (native resolution) values only when border has been created
            if border is not None:
                array[border] = band_file.array[border].astype(np.float32) / 10000.

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

    @staticmethod
    def proportion_fusion_diff(l2h_image, l2f_image, nodata_mask, nodata_value=2):
        """Compute proportion diff introduce by l2f on l2h"""
        # Reshape L2F
        res_factor = int(l2h_image.xRes / l2f_image.xRes)
        l2f_array_resize = l2f_image.array.copy()
        if res_factor != 1:
            l2f_array_resize = block_reduce(
                l2f_array_resize, block_size=(res_factor, res_factor), func=np.mean)
        l2h_array = l2h_image.array

        # compute percent_diff
        proportion_diff = (np.clip(l2h_array, 0.0001, 1.5) - np.clip(l2f_array_resize, 0.0001, 1.5)) / np.clip(l2h_array, 0.0001, 1.5)
        proportion_diff = np.clip(proportion_diff, -1., 1.)
        proportion_diff[nodata_mask.array == 0.] = np.nan
        proportion_diff_mask = np.ones(proportion_diff.shape)
        # compute mask of valid percentage
        proportion_diff_mask[np.isnan(proportion_diff)] = 0
        proportion_diff = np.nan_to_num(proportion_diff, nodata_value)
        return proportion_diff, proportion_diff_mask
