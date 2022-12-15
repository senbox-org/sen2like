#! /usr/bin/env python
# -*- coding: utf-8 -*-
# S. Saunier (TPZ) 2018


import logging

import os
import glob
import numpy as np
from osgeo import gdal
from skimage.transform import resize as skit_resize
from skimage.measure import block_reduce
import xarray as xr

from atmcor.get_s2_angles import get_angles_band_index
from core.QI_MTD.mtd import metadata
from core import S2L_config
from core.S2L_tools import out_stat
from core.products.product import S2L_Product
from core.image_file import S2L_ImageFile
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

class BRDFCoefficient:
    mtd = 'NONE'

    def __init__(self, product, image, band):
        self.product = product
        self.image = image
        self.band = product.bands_mapping[band]

    def check(self):
        return True

    def get(self):
        return None

    def get_cmatrix_full(self, KVOL_norm, KGEO_norm, KVOL_input, KGEO_input):
        return np.zeros(self.image.shape)

    def compute_Kvol(self, theta_s, theta_v, phi):
        return np.identity(theta_s.shape[0])


class ROYBRDFCoefficient(BRDFCoefficient):
    mtd = 'Roy and al. 2016'

    def __init__(self, product, image, band):
        super().__init__(product, image, band)
        self.band = band

    def check(self):
        return self.product.brdf_coefficients.get(self.band, {}).get("coef") is not None

    def get(self):
        brdf_coef_set = self.product.brdf_coefficients.get(self.band, {}).get("coef")
        log.debug('BRDF Coefficient Set :%s', brdf_coef_set)
        return brdf_coef_set

    def get_cmatrix_full(self, KVOL_norm, KGEO_norm, KVOL_input, KGEO_input):
        CMATRIX = normalized_brdf(KVOL_norm, KGEO_norm, KVOL_input, KGEO_input, self.get())
        return skit_resize(CMATRIX, self.image.array.shape)

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
    vr_file_glob_path = '*_BRDFinputs.nc'
    mtd = 'Vermote, E., C.O. Justice, et F.-M. Breon. 2009'

    def __init__(self, product, image, band, vr_matrix_dir):
        super().__init__(product, image, band)
        vr_files = glob.glob(os.path.join(vr_matrix_dir, self.vr_file_glob_path))
        self.vr_matrix = None
        self.vr_matrix_file = None
        self.tile = product.mtl.mgrs
        for file in vr_files:
            vr_matrix = xr.open_dataset(file)
            if vr_matrix.attrs['TILE'][-5:] == product.mtl.mgrs:
                log.info("Find VJB matrices : %s", file)
                self.vr_matrix = vr_matrix
                self.vr_matrix_resolution = int(self.vr_matrix.attrs['SPATIAL_RESOLUTION'])
                self.vr_matrix_file = file
                self.band_names = {
                    k: v for k, v in zip(self.vr_matrix.attrs['BANDS_NUMBER'], self.vr_matrix.attrs['BANDS'])}

                break  # Stop at the first correct file
            vr_matrix.close()

    def check(self):
        return self.vr_matrix is not None and self.band in self.vr_matrix.attrs['BANDS_NUMBER']

    def get(self):
        # Load datas
        if not self.check():
            return None
        V0 = self.vr_matrix['V0_tendency_' + self.band_names[self.band]] / 10000.0
        V1 = self.vr_matrix['V1_tendency_' + self.band_names[self.band]] / 10000.0
        R0 = self.vr_matrix['R0_tendency_' + self.band_names[self.band]] / 10000.0
        R1 = self.vr_matrix['R1_tendency_' + self.band_names[self.band]] / 10000.0
        ndvi_img = S2L_ImageFile(self.product.ndvi_filename)

        #  Resizing
        img_res = int(self.image.xRes)
        ndvi = _resize(ndvi_img.array, img_res / int(ndvi_img.xRes))
        log.debug("%s %s", img_res, self.vr_matrix_resolution)
        V0 = _resize(V0.data, img_res / self.vr_matrix_resolution)
        V1 = _resize(V1.data, img_res / self.vr_matrix_resolution)
        R0 = _resize(R0.data, img_res / self.vr_matrix_resolution)
        R1 = _resize(R1.data, img_res / self.vr_matrix_resolution)
        ndvi_min = _resize(self.vr_matrix.ndvi_min.data, img_res / self.vr_matrix_resolution) / 10000.0
        ndvi_max = _resize(self.vr_matrix.ndvi_max.data, img_res / self.vr_matrix_resolution) / 10000.0

        # Clip a tester:
        ndvi = np.where(ndvi < ndvi_min, ndvi_min, ndvi)
        ndvi = np.where(ndvi > ndvi_max, ndvi_max, ndvi)

        # regarde definition de np.clip sur la doc. & tester

        # ndvi = np.clip(ndvi, ndvi_min, ndvi_max)

        out_stat(ndvi_min, log, 'BRDF AUX - minimum ndvi')
        out_stat(ndvi_max, log, 'BRDF AUX - maximum ndvi')
        out_stat(ndvi, log, 'NDVI of input products')

        if S2L_config.config.getboolean('generate_intermediate_products'):
            ndvi_clip_img_path = os.path.join(S2L_config.config.get("wd"), self.product.name, 'ndvi_clipped.tif')
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
        if S2L_config.config.getboolean('generate_intermediate_products'):
            c_geo_image = self.image.duplicate(
                filepath=os.path.join(S2L_config.config.get("wd"), self.product.name, f'c_geo_{self.band}.tif'),
                array=c_geo,
                res=img_res
            )
            c_geo_image.write(DCmode=True, creation_options=['COMPRESS=LZW'])
            c_vol_image = self.image.duplicate(
                filepath=os.path.join(S2L_config.config.get("wd"), self.product.name, f'c_vol_{self.band}.tif'),
                array=c_vol,
                res=img_res
            )
            c_vol_image.write(DCmode=True, creation_options=['COMPRESS=LZW'])
        return 1, c_geo, c_vol

    def get_cmatrix_full(self, KVOL_norm, KGEO_norm, KVOL_input, KGEO_input):
        IM1 = self.image.array
        KVOL_NORM = skit_resize(KVOL_norm, IM1.shape)
        KGEO_NORM = skit_resize(KGEO_norm, IM1.shape)
        KVOL_INPUT = skit_resize(KVOL_input, IM1.shape)
        KGEO_INPUT = skit_resize(KGEO_input, IM1.shape)
        return normalized_brdf(KVOL_NORM, KGEO_NORM, KVOL_INPUT, KGEO_INPUT, self.get())

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

    def __init__(self):
        super().__init__()
        self._theta_s = None
        self._mean_delta_azimuth = []

    def initialize(self):
        self._theta_s = None
        self._mean_delta_azimuth = []

    def process(self, product: S2L_Product, image: S2L_ImageFile, band: str) -> S2L_ImageFile:

        log.info('Start')

        # brdf coefficiant class
        if S2L_config.config.get('nbar_methode') == 'VJB' and product.ndvi_filename is not None:
            self.brdf_coeff = VJBMatriceBRDFCoefficient(
                product, image, band, S2L_config.config.get('vjb_coeff_matrice_dir'))
            if not self.brdf_coeff.check():
                self.brdf_coeff = ROYBRDFCoefficient(product, image, band)
                log.info(
                    "None VJB matrice for tile %s and band %s, try to use ROY coeff in place",
                    product.mtl.mgrs, band
                )
        else:
            self.brdf_coeff = ROYBRDFCoefficient(product, image, band)

        # coeff for this band?
        if not self.brdf_coeff.check():
            log.info('No BRDF coefficient for %s', band)
            image_out = image
        else:
            if isinstance(self.brdf_coeff, VJBMatriceBRDFCoefficient):
                log.info("Use VJB coefficient matrices in : %s", self.brdf_coeff.vr_matrix_file)
            else:
                log.info("Use ROY coefficients")

            # Compute Kernels
            self._computeKernels(product, band)

            # NBAR correction
            OUT = self._nbar(product, image, band)

            # Format Output : duplicate, link  to product as parameter
            image_out = image.duplicate(self.output_file(product, band), array=OUT.astype(np.float32))
            if S2L_config.config.getboolean('generate_intermediate_products'):
                image_out.write(creation_options=['COMPRESS=LZW'])

        log.info('End')

        return image_out

    def postprocess(self, product: S2L_Product):
        """Set QI params

        Args:
            product (S2L_Product): product to post process
        """

        metadata.qi['BRDF_METHOD'] = self.brdf_coeff.mtd
        metadata.qi['CONSTANT_SOLAR_ZENITH_ANGLE'] = self._theta_s
        metadata.qi['MEAN_DELTA_AZIMUTH'] = np.mean(self._mean_delta_azimuth)

        # TODO : manage it with an abstract method in BRDFCoefficient
        if isinstance(self.brdf_coeff, VJBMatriceBRDFCoefficient) and self.brdf_coeff.vr_matrix_file:
            metadata.qi["VJB_COEFFICIENTS_FILENAME"] = os.path.basename(self.brdf_coeff.vr_matrix_file)

    def _computeKernels(self, product, band=None):
        lat = product.mtl.get_scene_center_coordinates()[1]
        scene_center_latitude = lat
        self._theta_s = get_mean_sun_angle(scene_center_latitude)

        log.debug('theta_s: %s', self._theta_s)

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
            angle_band_index = get_angles_band_index(band)
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
        self.KGEO_INPUT = li_sparse_kernel(SZA, VZA, SAA - VAA)

        # Prepare KVOL Input                      :
        log.debug('------------- KVOL INPUT COMPUTATION ------------------------------')
        self.KVOL_INPUT = self.brdf_coeff.compute_Kvol(SZA, VZA, SAA - VAA)
        # Prepare KGEO Norm    :
        SZA_NORM = np.ones(VAA.shape) * self._theta_s
        VZA_NORM = np.zeros(VAA.shape)
        DPHI_NORM = np.zeros(VAA.shape)

        log.debug('-------------------NORM-------------------------------------------')
        log.debug('------------- KGEO NORM COMPUTATION ------------------------------')
        self.KGEO_NORM = li_sparse_kernel(SZA_NORM, VZA_NORM, DPHI_NORM)
        log.debug('---- KVOL NORM COMPUTATION ---')
        self.KVOL_NORM = self.brdf_coeff.compute_Kvol(SZA_NORM, VZA_NORM, DPHI_NORM)

        log.debug('------------------------------------------------------------------')
        log.debug('--------------- KGEO INPUT STAT-----------------------------------')

        log.debug('---- KGEO INPUT ---')
        if S2L_config.config.getboolean('debug'):
            out_stat(self.KGEO_INPUT, log)

        log.debug('---- KVOL INPUT ---')
        if S2L_config.config.getboolean('debug'):
            out_stat(self.KVOL_INPUT, log)

        log.debug('---- KGEO NORM ---')
        if S2L_config.config.getboolean('debug'):
            out_stat(self.KGEO_NORM, log)

        log.debug('---- KVOL NORM ---')
        if S2L_config.config.getboolean('debug'):
            out_stat(self.KVOL_NORM, log)

    def _nbar(self, product, image, band):
        IM1 = image.array
        CMATRIX_full = self.brdf_coeff.get_cmatrix_full(
            self.KVOL_NORM, self.KGEO_NORM, self.KVOL_INPUT, self.KGEO_INPUT)
        U = IM1 >= 0
        if S2L_config.config.getboolean('debug'):
            log.debug('---- IMAGE before correction ---')
            out_stat(IM1[U], log)

        IM = CMATRIX_full
        U = IM >= 0

        OUT = CMATRIX_full * IM1
        # CORRECTION NBAR Limite a 20%
        PDIFF = np.divide((IM1-OUT)*100, IM1)
        # Difference Exceed + 20%  :
        OUT = np.where(PDIFF > 20,  IM1 + 0.2*IM1, OUT)
        OUT = np.where(PDIFF < -20, IM1 - 0.2*IM1, OUT)

        if S2L_config.config.getboolean('debug'):
            log.debug('---- IMAGE after correction ( before removing negative values ---')
            out_stat(OUT, log)

        OUT[IM1 <= 0] = 0

        return OUT


def _resize(array, resolution_ratio: float):
    """Multiplie shape of array by resolution_ratio
    """
    if resolution_ratio == 1:
        return array
    elif resolution_ratio.is_integer():
        return block_reduce(array, (int(resolution_ratio), int(resolution_ratio)), func=np.mean)
    else:
        out_shape = tuple(round(s / resolution_ratio) for s in array.shape)
        return skit_resize(array, out_shape, order=1, preserve_range=True)
