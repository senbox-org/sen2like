#! /usr/bin/env python
# -*- coding: utf-8 -*-
# S. Saunier (TPZ) 2018


import logging

import numpy as np
from osgeo import gdal
from skimage.transform import resize

from core.S2L_config import config
from core.QI_MTD.mtd import metadata
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
    ct = np.float(np.pi / 180.0)
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
    overlap = np.divide(1.0, np.pi) * (t - sin_t * cos_t) \
              * (sec_theta_s_p + sec_theta_v_p)
    # Compute KGEO :
    t = - sec_theta_s_p - sec_theta_v_p + 0.5 * (1 + cos_zetha_p) * sec_theta_v_p * sec_theta_v_p
    K_GEO = overlap - sec_theta_s_p - sec_theta_v_p + 0.5 * (1 + cos_zetha_p) * sec_theta_s_p * sec_theta_v_p

    return K_GEO


def ross_thick(theta_s, theta_v, phi):
    # Roujean et al. [32].
    # Implement old formula of MODIS ATBD 1999 (pp 13) ,
    # But different from Roujean and Al

    ct = np.float(np.pi / 180.0)
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


def normalized_brdf(KVOL_norm, KGEO_norm, KVOL_input, KGEO_input, coef):
    """
    :param KVOL_norm: Li_sparse brdf Kernel  (np.array) for geometry to normalize
    :param KGEO_norm: Ross Thick brdf Kernel (np.array) for geometry to normalize
    :param KVOL_input: Li_sparse brdf Kernel  (np.array) for geometry as input
    :param KGEO_input: Ross Thick brdf Kernel (np.array) for geometry as input
    :param coef: c-factor coefficients    (f_iso,f_vol,f_geo)
    :return: OUT as np.array
    """

    # Create identity Matrix :
    id_M = np.ones(KVOL_norm.shape)

    f_iso = coef[0]
    f_geo = coef[1]
    f_vol = coef[2]
    numerator = f_iso * id_M + f_geo * KGEO_norm + f_vol * KVOL_norm
    denominator = f_iso * id_M + f_geo * KGEO_input + f_vol * KVOL_input
    CMATRIX = numerator / denominator

    return CMATRIX


# END BRDF KERNEL Functions :

def get_brdf_coefficient(product, band):
    return product.brdf_coefficients.get(band, {}).get("coef")


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

    def process(self, product, image, band):

        log.info('Start')

        # coeff for this band?
        if get_brdf_coefficient(product, band) is None:
            log.warning('No BRDF coefficient for {}'.format(band))
            image_out = image
        else:
            # Compute Kernels
            self._computeKernels(product, band)

            # NBAR correction
            OUT = self._nbar(product, image, band)

            # Format Output : duplicate, link  to product as parameter
            image_out = image.duplicate(self.output_file(product, band), array=OUT.astype(np.float32))
            if config.getboolean('generate_intermediate_products'):
                image_out.write(creation_options=['COMPRESS=LZW'])

        log.info('End')

        return image_out

    def _computeKernels(self, product, band=None):
        lat = product.mtl.get_scene_center_coordinates()[1]
        scene_center_latitude = lat
        theta_s = get_mean_sun_angle(scene_center_latitude)
        metadata.qi['CONSTANT_SOLAR_ZENITH_ANGLE'] = theta_s
        log.debug('theta_s: {}'.format(theta_s))

        # Read TP , unit = degree, scale=100
        src_ds = gdal.Open(product.mtl.angles_file)
        nBands = src_ds.RasterCount

        if nBands == 4:
            # VAA, VZA, SAA, SZA
            VAA = src_ds.GetRasterBand(1).ReadAsArray().astype(np.float32) / 100.0
            VZA = src_ds.GetRasterBand(2).ReadAsArray().astype(np.float32) / 100.0
            SAA = src_ds.GetRasterBand(3).ReadAsArray().astype(np.float32) / 100.0
            SZA = src_ds.GetRasterBand(4).ReadAsArray().astype(np.float32) / 100.0

        else:
            # VAA for each band, VZA for each band, SAA, SZZ
            angle_band_index = product.get_angles_band_index(band)
            VAA = src_ds.GetRasterBand(angle_band_index + 1).ReadAsArray().astype(np.float32) / 100.0
            VZA = src_ds.GetRasterBand(13 + angle_band_index + 1).ReadAsArray().astype(np.float32) / 100.0
            SAA = src_ds.GetRasterBand(nBands - 1).ReadAsArray().astype(np.float32) / 100.0
            SZA = src_ds.GetRasterBand(nBands).ReadAsArray().astype(np.float32) / 100.0

        # close
        src_ds = None
        metadata.qi['MEAN_DELTA_AZIMUTH'] = np.mean(SAA - VAA) % 360

        if config.getboolean('debug'):
            out_stat(VAA, 'VAA')
            out_stat(VZA, 'VZA')
            out_stat(SAA, 'SAA')
            out_stat(SZA, 'SZA')

        # Prepare KGEO Input
        log.debug('--------------------  INPUT  --------------------------------------')
        log.debug('---- ---------KGEO INPUT COMPUTATION ------------------------------')
        self.KGEO_INPUT = li_sparse_kernel(SZA, VZA, SAA - VAA)

        # Prepare KVOL Input                      :
        log.debug('------------- KVOL INPUT COMPUTATION ------------------------------')
        self.KVOL_INPUT = ross_thick(SZA, VZA, SAA - VAA)
        # Prepare KGEO Norm    :
        SZA_NORM = np.ones(VAA.shape) * theta_s
        VZA_NORM = np.zeros(VAA.shape)
        DPHI_NORM = np.zeros(VAA.shape)

        log.debug('-------------------NORM-------------------------------------------')
        log.debug('------------- KGEO NORM COMPUTATION ------------------------------')
        self.KGEO_NORM = li_sparse_kernel(SZA_NORM, VZA_NORM, DPHI_NORM)
        log.debug('---- KVOL NORM COMPUTATION ---')
        self.KVOL_NORM = ross_thick(SZA_NORM, VZA_NORM, DPHI_NORM)

        log.debug('------------------------------------------------------------------')
        log.debug('--------------- KGEO INPUT STAT-----------------------------------')

        log.debug('---- KGEO INPUT ---')
        if config.getboolean('debug'):
            out_stat(self.KGEO_INPUT)

        log.debug('---- KVOL INPUT ---')
        if config.getboolean('debug'):
            out_stat(self.KVOL_INPUT)

        log.debug('---- KGEO NORM ---')
        if config.getboolean('debug'):
            out_stat(self.KGEO_NORM)

        log.debug('---- KVOL NORM')
        if config.getboolean('debug'):
            out_stat(self.KVOL_NORM)

    def _nbar(self, product, image, band):
        # Get BRDF coefficients
        brdf_coef_set = get_brdf_coefficient(product, band)

        log.debug('BRDF Coefficient Set :{}'.format(brdf_coef_set))

        CMATRIX = normalized_brdf(self.KVOL_NORM, self.KGEO_NORM,
                                  self.KVOL_INPUT, self.KGEO_INPUT,
                                  brdf_coef_set)
        IM1 = image.array
        U = IM1 >= 0
        if config.getboolean('debug'):
            out_stat(IM1[U])

        CMATRIX_full = resize(CMATRIX, IM1.shape)
        IM = CMATRIX_full
        U = IM >= 0
        if config.getboolean('debug'):
            out_stat(IM[U])

        OUT = CMATRIX_full * IM1
        OUT[IM1 <= 0] = 0

        return OUT


def out_stat(input_matrix, label=""):
    log.debug('Maximum {} : {}'.format(label, np.max(input_matrix)))
    log.debug('Mean {} : {}'.format(label, np.mean(input_matrix)))
    log.debug('Std dev {} : {}'.format(label, np.std(input_matrix)))
    log.debug('Minimum {} : {}'.format(label, np.min(input_matrix)))
