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

import glob
import logging
import os
import re
from abc import ABC, abstractmethod
from collections import OrderedDict
from dataclasses import dataclass
from datetime import datetime

import numpy as np
import xarray as xr
from osgeo import gdal
from skimage.measure import block_reduce
from skimage.transform import resize as skit_resize

from atmcor.get_s2_angles import get_angles_band_index
from core import S2L_config
from core.image_file import S2L_ImageFile
from core.products.product import S2L_Product
from core.S2L_tools import out_stat
from s2l_processes.S2L_Process import S2L_Process

log = logging.getLogger("Sen2Like")


# BRDF KERNEL Functions :

def li_sparse_kernel(theta_s, theta_v, phi):
    """
    Function compute the geometric  BRDF LiSpare Kernel  derived from surface scattering
    and geometry shadow casting theory (Li & Strahler, 1992)
    Kgeo developped by Wanner et Al. (1995)

        :param theta_s: solar zenith angle (degree)
        :param theta_v: view zenith angle (degree)
        :param phi: delta azimuth (view - phi ) by convention between 0 and pi (degree)
        :return: K_GEO,cos_t,cos_t_valid
                   K_GEO       : Brdf Kernel
                   cos_t_valid : Flag Valid K_Geo

    Voir le tuto https://xlim-sic.labo.univ-poitiers.fr/logiciels/rView/Fichiers/documentation_technique.pdf
    Crown relative height and shape parameters :
    """
    h_sur_b = 2
    b_sur_r = 1
    ct = float(np.pi / 180.0)
    # Convert to radiance
    theta_s_r = np.multiply(ct, theta_s)
    theta_v_r = np.multiply(ct, theta_v)
    phi_r = np.multiply(ct, phi)

    theta_s_p = np.arctan(b_sur_r * np.tan(theta_s_r))
    theta_v_p = np.arctan(b_sur_r * np.tan(theta_v_r))
    cos_zetha_p = np.cos(theta_s_p) * np.cos(theta_v_p) + np.sin(theta_s_p) * np.sin(theta_v_p) * np.cos(phi_r)

    D = np.power(
        np.power(np.tan(theta_s_p), 2) +
        np.power(np.tan(theta_v_p), 2) -
        2 * np.tan(theta_s_p) * np.tan(theta_v_p) * np.cos(phi_r), 0.5)
    sec_theta_s_p = np.divide(1.0, np.cos(theta_s_p))
    sec_theta_v_p = np.divide(1.0, np.cos(theta_v_p))

    # Compute t :
    numerator = np.power(np.power(D, 2) + np.power(np.tan(theta_s_p) * np.tan(theta_v_p) * np.sin(phi_r), 2), 0.5)
    denominator = sec_theta_s_p + sec_theta_v_p

    cos_t = h_sur_b * np.divide(numerator, denominator)
    # Correct point with no overlapping
    cos_t[cos_t <= -1] = -1
    cos_t[cos_t >= 1] = 1

    sin_t = np.power(1 - cos_t * cos_t, 0.5)

    t = np.arccos(cos_t)

    # Compute overlap value between the view and the solar shadow :
    overlap = np.divide(1.0, np.pi) * (t - sin_t * cos_t) * (sec_theta_s_p + sec_theta_v_p)
    # Compute KGEO :
    k_geo = overlap - sec_theta_s_p - sec_theta_v_p + 0.5 * (1 + cos_zetha_p) * sec_theta_s_p * sec_theta_v_p

    return k_geo


def normalized_brdf(KVOL_norm, KGEO_norm, KVOL_input, KGEO_input, coef):
    """
    :param KVOL_norm: Li_sparse brdf Kernel  (np.array) for geometry to normalize
    :param KGEO_norm: Ross Thick brdf Kernel (np.array) for geometry to normalize
    :param KVOL_input: Li_sparse brdf Kernel  (np.array) for geometry as input
    :param KGEO_input: Ross Thick brdf Kernel (np.array) for geometry as input
    :param coef: c-factor coefficients    (f_iso,f_geo,f_vol)
    :return: OUT as np.array
    """

    f_iso = coef[0]
    f_geo = coef[1]
    f_vol = coef[2]
    numerator = f_iso + f_geo * KGEO_norm + f_vol * KVOL_norm
    denominator = f_iso + f_geo * KGEO_input + f_vol * KVOL_input
    CMATRIX = numerator / denominator

    return CMATRIX


# END BRDF KERNEL Functions :

@dataclass
class BandParam:
    """
    Internal dataclasses for S2L_Nbar._band_param dict values
    """
    band_name: str
    # brdf_coeff: None|BRDFCoefficient
    KVOL_NORM: None
    KGEO_NORM: None
    KVOL_INPUT: None
    KGEO_INPUT: None


class BRDFCoefficient(ABC):
    mtd = 'NONE'

    def __init__(self, product):
        self.product = product

    def _get_band(self, band):
        return self.product.bands_mapping[band]

    @abstractmethod
    def check(self, band) -> bool:
        ...

    @abstractmethod
    def get_cmatrix_full(self, image: S2L_ImageFile, band_param: BandParam):
        ...

    @abstractmethod
    def compute_Kvol(self, theta_s, theta_v, phi):
        ...


class ROYBRDFCoefficient(BRDFCoefficient):
    mtd = 'Roy and al. 2016'

    def _get_band(self, band):
        return band

    def check(self, band):
        return self.product.brdf_coefficients.get(self._get_band(band), {}).get("coef") is not None

    def _get(self, band):
        brdf_coef_set = self.product.brdf_coefficients.get(self._get_band(band), {}).get("coef")
        log.debug('BRDF Coefficient Set :%s', brdf_coef_set)
        return brdf_coef_set

    def get_cmatrix_full(self, image: S2L_ImageFile, band_param: BandParam):
        CMATRIX = normalized_brdf(
            band_param.KVOL_NORM,
            band_param.KGEO_NORM,
            band_param.KVOL_INPUT,
            band_param.KGEO_INPUT,
            self._get(band_param.band_name)
        )
        return skit_resize(CMATRIX, image.array.shape)

    def compute_Kvol(self, theta_s, theta_v, phi):
        """Compute Kvol with Ross Tick methode
        Roujean et al. [32].
        Implement old formula of MODIS ATBD 1999 (pp 13) ,
        But different from Roujean and Al
        """

        ct = float(np.pi / 180.0)
        # Convert to radiance
        theta_s_r = np.multiply(ct, theta_s)
        theta_v_r = np.multiply(ct, theta_v)
        phi_r = np.multiply(ct, phi)
        cos_zetha = np.cos(theta_s_r) * np.cos(theta_v_r) + np.sin(theta_s_r) * np.sin(theta_v_r) * np.cos(phi_r)
        zetha = np.arccos(cos_zetha)
        numerator = (np.pi / 2.0 - zetha) * np.cos(zetha) + np.sin(zetha)
        denominator = np.cos(theta_v_r) + np.cos(theta_s_r)
        #    Kvol = ( numerator / denominator ) - np.pi / 4.0
        Kvol = (4.0 / (3.0 * np.pi)) * (numerator / denominator) - (1.0 / 3.0)

        return Kvol


class VJBMatriceBRDFCoefficient(BRDFCoefficient):

    mtd = 'Vermote, E., C.O. Justice, et F.-M. Breon. 2009'

    # AUX DATA filename sample : S2__USER_AUX_HABA___UV___20221027T000101_V20190105T103429_20191231T103339_T31TFJ_MLSS2_MO.nc
    # Note that group 6 (20221027T000101) is composed by production day + T + 00 + version number -> this is not a real date and time
    # groupe 7 is validity start date
    # groupe 8 is validity end date
    AUX_FILE_EXPR = re.compile(
        "S2(.)_(.{4})_(.{3})_(.{6})_(.{4})_(\\d{8}T\\d{6})_V(\\d{8}T\\d{6})_(\\d{8}T\\d{6})_T(.{5})_(.{5})_(.{2})\\.nc"
    )

    def __init__(self, product, vr_matrix_dir, generate_intermediate_products):

        super().__init__(product)

        self.vr_matrix = None
        self._generate_intermediate_products = generate_intermediate_products
        self.vr_matrix_file = self._select_vr_file(vr_matrix_dir)

        if self.vr_matrix_file:
            log.info("Find VJB matrices : %s", self.vr_matrix_file)
            # do not use xarray cache to avoid memomy leak
            self.vr_matrix = xr.open_dataset(self.vr_matrix_file, cache=False)
            self.vr_matrix_resolution = int(self.vr_matrix.attrs['SPATIAL_RESOLUTION'])
            self.vr_matrix_bands = self.vr_matrix.attrs['BANDS_NUMBER']
            self.vr_matrix.close()

    def _select_vr_file(self, aux_data_folder_path) -> str|None:
        """Select aux data file in the given dir path having tile and validity dates
        that match product tile and acquisition date.
        If multiple files match, select the most recent.

        Args:
            aux_data_folder_path (str): aux data folder path

        Returns:
            str: aux data file path, None if no fil match
        """

        # First filter aux data files on tile
        vr_file_glob_path = f"S2*_T{self.product.mgrs}*.nc"
        vr_files = glob.glob(os.path.join(aux_data_folder_path, vr_file_glob_path))

        # We will index candidate files by production day/version number pair
        _candidate_vr_files = {}

        # attempt to select on validity dates
        for file_path in vr_files:
            aux_data_file_name = os.path.basename(file_path)
            match = self.AUX_FILE_EXPR.match(aux_data_file_name)
            if match:
                validity_start = datetime.strptime(match.group(7), "%Y%m%dT%H%M%S")
                validity_start = validity_start.replace(microsecond=0)
                validity_end = datetime.strptime(match.group(8), "%Y%m%dT%H%M%S")
                validity_end = validity_end.replace(microsecond=999999)

                if validity_start < self.product.acqdate < validity_end:
                    # validity dates match, index it on production day/version number pair
                    _idx = match.group(6)
                    _candidate_vr_files[_idx] = file_path

        # found file
        if _candidate_vr_files:
            # sort candidates by production day/version number pair
            _candidate_vr_files = OrderedDict(sorted(_candidate_vr_files.items()))
            # get latest
            return _candidate_vr_files.popitem(last=True)[1]

        # no file found
        return None

    def check(self, band):
        return self.vr_matrix is not None and self._get_band(band) in self.vr_matrix_bands

    def _get(self, image, band):
        # Load datas
        if not self.check(band):
            return None

        # V0 <=> V_intercept_Bxx
        # V1 <=> V_slope_Bxx
        # R0 <=> R_intercept_Bxx
        # R1 <=> R_slope_Bxx

        V0 = self.vr_matrix[f'V_intercept_{self._get_band(band)}'] / 10000.0
        V1 = self.vr_matrix[f'V_slope_{self._get_band(band)}'] / 10000.0
        R0 = self.vr_matrix[f'R_intercept_{self._get_band(band)}'] / 10000.0
        R1 = self.vr_matrix[f'R_slope_{self._get_band(band)}'] / 10000.0

        ndvi_img = S2L_ImageFile(self.product.ndvi_filename)

        #  Resizing
        img_res = int(image.xRes)
        ndvi = _resize(ndvi_img.array, img_res / int(ndvi_img.xRes))
        log.debug("%s %s", img_res, self.vr_matrix_resolution)
        V0 = _resize(V0.data, img_res / self.vr_matrix_resolution)
        V1 = _resize(V1.data, img_res / self.vr_matrix_resolution)
        R0 = _resize(R0.data, img_res / self.vr_matrix_resolution)
        R1 = _resize(R1.data, img_res / self.vr_matrix_resolution)
        ndvi_min = _resize(self.vr_matrix.NDVImin.data, img_res / self.vr_matrix_resolution) / 10000.0
        ndvi_max = _resize(self.vr_matrix.NDVImax.data, img_res / self.vr_matrix_resolution) / 10000.0

        # Clip a tester:
        ndvi = np.where(ndvi < ndvi_min, ndvi_min, ndvi)
        ndvi = np.where(ndvi > ndvi_max, ndvi_max, ndvi)

        # regarde definition de np.clip sur la doc. & tester

        # ndvi = np.clip(ndvi, ndvi_min, ndvi_max)

        out_stat(ndvi_min, log, 'BRDF AUX - minimum ndvi')
        out_stat(ndvi_max, log, 'BRDF AUX - maximum ndvi')
        out_stat(ndvi, log, 'NDVI of input products')

        _working_dir = self.product.working_dir

        if self._generate_intermediate_products:
            ndvi_clip_img_path = os.path.join(_working_dir, 'ndvi_clipped.tif')
            if not os.path.isfile(ndvi_clip_img_path):
                ndvi_clip_img = ndvi_img.duplicate(
                    filepath=ndvi_clip_img_path,
                    array=ndvi,
                    res=img_res
                )
                ndvi_clip_img.write(DCmode=True, creation_options=['COMPRESS=LZW'])

        # Compute coefficiant
        c_vol = V0 + V1 * ndvi  # c_geo = f_geo/f_iso
        c_geo = R0 + R1 * ndvi  # c_vol = f_vol/f_iso
        log.debug("c_geo have %s NaN", np.isnan(c_geo).sum())
        log.debug("c_vol have %s NaN", np.isnan(c_vol).sum())
        np.nan_to_num(c_geo, copy=False)
        np.nan_to_num(c_vol, copy=False)
        if self._generate_intermediate_products:
            c_geo_image = image.duplicate(
                filepath=os.path.join(_working_dir, f'c_geo_{self._get_band(band)}.tif'),
                array=c_geo,
                res=img_res
            )
            c_geo_image.write(DCmode=True, creation_options=['COMPRESS=LZW'])
            c_vol_image = image.duplicate(
                filepath=os.path.join(_working_dir, f'c_vol_{self._get_band(band)}.tif'),
                array=c_vol,
                res=img_res
            )
            c_vol_image.write(DCmode=True, creation_options=['COMPRESS=LZW'])
        return 1, c_geo, c_vol

    def get_cmatrix_full(self, image: S2L_ImageFile, band_param: BandParam):
        IM1 = image.array
        KVOL_NORM = skit_resize(band_param.KVOL_NORM, IM1.shape)
        KGEO_NORM = skit_resize(band_param.KGEO_NORM, IM1.shape)
        KVOL_INPUT = skit_resize(band_param.KVOL_INPUT, IM1.shape)
        KGEO_INPUT = skit_resize(band_param.KGEO_INPUT, IM1.shape)
        return normalized_brdf(
            KVOL_NORM,
            KGEO_NORM,
            KVOL_INPUT,
            KGEO_INPUT,
            self._get(image, band_param.band_name)
        )

    def compute_Kvol(self, theta_s, theta_v, phi):
        """Compute Kvol with Maignan methode
        Improvement of the Ross Thick Kernel accounting for Hot Spot

        Bidirectional reflectance of Earth targets: Evaluation of analytical models
        using a large set of spaceborne measurements with emphasis on the
        Hot Spot

        F. Maignana, F.-M. Breon, R. Lacaze Remote Sensing of Environment 90 (2004) 210–220
        (Equation 12)
        """
        ct = float(np.pi / 180.0)
        # Convert to radiance
        theta_s_r = np.multiply(ct, theta_s)
        theta_v_r = np.multiply(ct, theta_v)
        phi_r = np.multiply(ct, phi)
        cos_zetha = np.cos(theta_s_r) * np.cos(theta_v_r) + np.sin(theta_s_r) * np.sin(theta_v_r) * np.cos(phi_r)
        zetha = np.arccos(cos_zetha)
        zetha_0 = ct * 1.5
        numerator = (np.pi / 2.0 - zetha) * np.cos(zetha) + np.sin(zetha)
        denominator = np.cos(theta_v_r) + np.cos(theta_s_r)
        hot_spot_factor = (1 + (1 + (zetha/zetha_0))**-1)
        #    Kvol = ( numerator / denominator ) - np.pi / 4.0
        Kvol = (4.0 / (3.0 * np.pi)) * (numerator / denominator) * hot_spot_factor - (1.0 / 3.0)

        return Kvol


def get_mean_sun_angle(scene_center_latitude):
    # Polynomial coefficient to retrieve the mean sun zenith angle (SZA)
    # as a function of the central latitude (eq. 4)
    k0 = 31.0076
    k1 = -0.1272
    k2 = 0.01187
    k3 = 2.40E-05
    k4 = -9.48E-07
    k5 = -1.95E-09
    k6 = 6.15E-11
    theta_s = k6 * np.power(scene_center_latitude, 6) + \
              k5 * np.power(scene_center_latitude, 5) + \
              k4 * np.power(scene_center_latitude, 4) + \
              k3 * np.power(scene_center_latitude, 3) + \
              k2 * np.power(scene_center_latitude, 2) + \
              k1 * np.power(scene_center_latitude, 1) + k0

    return theta_s


class S2L_Nbar(S2L_Process):

    def __init__(self, generate_intermediate_products: bool):
        super().__init__(generate_intermediate_products)
        self._theta_s = None
        self._mean_delta_azimuth = []
        self._brdf_coeff: BRDFCoefficient

    def preprocess(self, product: S2L_Product):
        """Compute theta_s

        Args:
            product (S2L_Product): product to preprocess
        """
        log.info("Select BRDF stategy for %s", product.name)

        lat = product.mtl.get_scene_center_coordinates()[1]
        scene_center_latitude = lat
        self._theta_s = get_mean_sun_angle(scene_center_latitude)
        # update method if any
        if S2L_config.config.get('nbar_methode') == 'VJB' and product.ndvi_filename is not None:
            self._brdf_coeff = VJBMatriceBRDFCoefficient(
                product,
                S2L_config.config.get('vjb_coeff_matrice_dir'),
                self.generate_intermediate_products
            )
            log.info("Use VJB coefficient matrices in : %s", self._brdf_coeff.vr_matrix_file)
        else:
            self._brdf_coeff = ROYBRDFCoefficient(product)
            log.info("Use ROY coefficients")

    def process(self, product: S2L_Product, image: S2L_ImageFile, band: str) -> S2L_ImageFile:

        _band_param = BandParam(band, None, None, None, None)

        # coeff for this band?
        if not self._brdf_coeff.check(band):
            log.info('No BRDF coefficient for %s', band)
            image_out = image
        else:
            # Compute Kernels
            self._computeKernels(product, _band_param)

            # NBAR correction
            OUT = self._nbar(image, _band_param)

            # Format Output : duplicate, link  to product as parameter
            image_out = image.duplicate(self.output_file(product, band), array=OUT.astype(np.float32))
            if self.generate_intermediate_products:
                image_out.write(creation_options=['COMPRESS=LZW'])

        return image_out

    def postprocess(self, product: S2L_Product):
        """Set QI params

        Args:
            product (S2L_Product): product to post process
        """

        product.metadata.qi['BRDF_METHOD'] = self._brdf_coeff.mtd
        product.metadata.qi['CONSTANT_SOLAR_ZENITH_ANGLE'] = self._theta_s
        product.metadata.qi['MEAN_DELTA_AZIMUTH'] = np.mean(self._mean_delta_azimuth)

        # TODO : manage it with an abstract method in BRDFCoefficient
        if isinstance(self._brdf_coeff, VJBMatriceBRDFCoefficient) and self._brdf_coeff.vr_matrix_file:
            product.metadata.qi["VJB_COEFFICIENTS_FILENAME"] = os.path.basename(self._brdf_coeff.vr_matrix_file)
            try:
                self._brdf_coeff.vr_matrix.close()
            except:
                log.warning("Unable to close VJB coef file %s", self._brdf_coeff.vr_matrix_file)
                log.warning("That could lead to memory leak")

    def _computeKernels(self, product: S2L_Product, band_param: BandParam):

        log.debug('theta_s: %s', self._theta_s)
        log.info("Compute kernels")
        # Read TP , unit = degree, scale=100
        src_ds = gdal.Open(product.angles_file)
        nBands = src_ds.RasterCount

        if nBands == 4:
            # VAA, VZA, SAA, SZA
            VAA = src_ds.GetRasterBand(1).ReadAsArray().astype(np.float32) / 100.0
            VZA = src_ds.GetRasterBand(2).ReadAsArray().astype(np.float32) / 100.0
            SAA = src_ds.GetRasterBand(3).ReadAsArray().astype(np.float32) / 100.0
            SZA = src_ds.GetRasterBand(4).ReadAsArray().astype(np.float32) / 100.0

        else:
            # VAA for each band, VZA for each band, SAA, SZZ
            angle_band_index = get_angles_band_index(band_param.band_name)
            VAA = src_ds.GetRasterBand(angle_band_index + 1).ReadAsArray().astype(np.float32) / 100.0
            VZA = src_ds.GetRasterBand(13 + angle_band_index + 1).ReadAsArray().astype(np.float32) / 100.0
            SAA = src_ds.GetRasterBand(nBands - 1).ReadAsArray().astype(np.float32) / 100.0
            SZA = src_ds.GetRasterBand(nBands).ReadAsArray().astype(np.float32) / 100.0

        # close
        src_ds = None

        self._mean_delta_azimuth.append(np.mean(SAA - VAA) % 360)

        if S2L_config.config.getboolean('debug'):
            out_stat(VAA, log, 'VAA')
            out_stat(VZA, log, 'VZA')
            out_stat(SAA, log, 'SAA')
            out_stat(SZA, log, 'SZA')

        # Prepare KGEO Input
        log.debug('--------------------  INPUT  --------------------------------------')
        log.debug('---- ---------KGEO INPUT COMPUTATION ------------------------------')
        band_param.KGEO_INPUT = li_sparse_kernel(SZA, VZA, SAA - VAA)

        # Prepare KVOL Input                      :
        log.debug('------------- KVOL INPUT COMPUTATION ------------------------------')
        band_param.KVOL_INPUT = self._brdf_coeff.compute_Kvol(SZA, VZA, SAA - VAA)
        # Prepare KGEO Norm    :
        SZA_NORM = np.ones(VAA.shape) * self._theta_s
        VZA_NORM = np.zeros(VAA.shape)
        DPHI_NORM = np.zeros(VAA.shape)

        log.debug('-------------------NORM-------------------------------------------')
        log.debug('------------- KGEO NORM COMPUTATION ------------------------------')
        band_param.KGEO_NORM = li_sparse_kernel(SZA_NORM, VZA_NORM, DPHI_NORM)
        log.debug('---- KVOL NORM COMPUTATION ---')
        band_param.KVOL_NORM = self._brdf_coeff.compute_Kvol(SZA_NORM, VZA_NORM, DPHI_NORM)

        log.debug('------------------------------------------------------------------')
        log.debug('--------------- KGEO INPUT STAT-----------------------------------')

        log.debug('---- KGEO INPUT ---')
        if S2L_config.config.getboolean('debug'):
            out_stat(band_param.KGEO_INPUT, log)

        log.debug('---- KVOL INPUT ---')
        if S2L_config.config.getboolean('debug'):
            out_stat(band_param.KVOL_INPUT, log)

        log.debug('---- KGEO NORM ---')
        if S2L_config.config.getboolean('debug'):
            out_stat(band_param.KGEO_NORM, log)

        log.debug('---- KVOL NORM ---')
        if S2L_config.config.getboolean('debug'):
            out_stat(band_param.KVOL_NORM, log)

    def _nbar(self, image: S2L_ImageFile, band_param: BandParam):

        log.info("Get CMATRIX")

        input_img_array = image.array

        CMATRIX_full = self._brdf_coeff.get_cmatrix_full(image, band_param)

        if S2L_config.config.getboolean('debug'):
            U = input_img_array >= 0
            log.debug('---- IMAGE before correction ---')
            out_stat(input_img_array[U], log)

        log.info("Apply CMATRIX")

        output_image_array = CMATRIX_full * input_img_array

        # CORRECTION NBAR Limite a 20%
        output_image_array = np.clip(
            output_image_array,
            0.8*input_img_array,
            1.2*input_img_array
        )

        if S2L_config.config.getboolean('debug'):
            log.debug('---- IMAGE after correction ( before removing negative values ---')
            out_stat(output_image_array, log)

        output_image_array[input_img_array <= 0] = 0

        return output_image_array


def _resize(array, resolution_ratio: float):
    """Multiplie shape of array by resolution_ratio
    """
    if resolution_ratio == 1:
        return array

    if resolution_ratio.is_integer():
        return block_reduce(array, (int(resolution_ratio), int(resolution_ratio)), func=np.mean)

    out_shape = tuple(round(s / resolution_ratio) for s in array.shape)
    return skit_resize(array, out_shape, order=1, preserve_range=True)
