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


import datetime as dt
import logging
import os

import numpy as np

from atmcor.atmospheric_parameters import ATMO_parameter
from atmcor.cams_data_reader import ECMWF_Product
from atmcor.smac import smac
from core import S2L_config
from core.image_file import S2L_ImageFile
from core.products.product import S2L_Product
from grids.grids import GridsConverter
from s2l_processes.S2L_Process import S2L_Process

log = logging.getLogger("Sen2Like")


def get_cams_configuration():
    return {
        "default": S2L_config.config.get('cams_dir'),
        "hourly": S2L_config.config.get('cams_hourly_dir'),
        "daily": S2L_config.config.get('cams_daily_dir'),
        "climatology": S2L_config.config.get('cams_climatology_dir')
    }


def get_smac_coefficients(product, band):
    filename = product.get_smac_filename(band)
    if filename is None:
        return None

    # smac coefficient are in the smac package
    smac_directory = os.path.dirname(os.path.abspath(smac.__file__))
    smac_file = os.path.join(smac_directory, 'COEFS', filename)
    if os.path.exists(smac_file):
        return smac_file
    return None


class S2L_Atmcor(S2L_Process):
    """
    Atmospheric Correction processing block class.
    Only able to run SMAC atmo corr as sen2cor cannot be run by band.
    If use_sen2cor=True in the config, then this processing block should be disabled
    Notice that use_sen2cor and doAtmcor can be overridden depending on the type of product to process.
    See sen2like module about
    """

    def __init__(self, generate_intermediate_products: bool):
        super().__init__(generate_intermediate_products)
        self._mgrs = GridsConverter()
        # default params
        self.uH2O = 2.0  # Water Vapor content - unit: g.cm-2
        self.uO3 = 0.331  # Ozone content - unit: cm-atm , 0.3 cm-atm = 300 Dobson Units
        self.pressure = 1013.095  # Pressure - unit: hpa
        self.taup550 = 0.2  # taup550 - unit: unitless

    def smac_correction(self, product, array_in, band):
        """
        Atmospheric correction with SMAC
        Includes CAMS data access.
        :param product: product object
        :param array_in: TOA image data (numpy array)
        :param band: band
        :return: SURF image DATA (numpy array)
        """

        log.debug("SMAC Correction")
        mtl = product.mtl

        # # ----------------------------------------------------------------------------------
        # # Prepare RGB composite TOA Reflectance
        # # ----------------------------------------------------------------------------------

        # taup550 = pick_macc_aot_value(ncdf_filename[0], Longitude, Latitude, UTC_ARR)

        # # ----------------------------------------------------------------------------------
        # # 7. Perform a Simple Atmospheric Correction using SMAC
        # # for all Landsat bands and for TOA reflectances ranging from 0.1 to 1.0 with a step of 0.01
        # # ----------------------------------------------------------------------------------

        theta_s = np.double(mtl.sun_zenith_angle)
        phi_s = np.double(mtl.sun_azimuth_angle)

        theta_v = 0  # View Zenith Angle Landsat (Nadir)
        phi_v = 0  # View Azimuth Angle Landsat (Nadir)

        # Atmospheric parameters retrieve from CAMS :
        r_toa = np.arange(101) / 100.
        r_surf_SMAC = np.zeros(101)

        # # Apply correction

        # Load SMAC coefficients
        coef_file = get_smac_coefficients(product, band)
        log.debug(coef_file)
        if coef_file is None:
            log.error("No smac coefficients for %s", band)
            return array_in

        smac_coefs = smac.coeff(coef_file)

        # Run SMAC for r_toa ranging from 0.0 to 1.0
        for i in range(101):
            r_surf_SMAC[i] = smac.smac_inv(
                r_toa[i], theta_s, phi_s,
                theta_v, phi_v, self.pressure,
                self.taup550, self.uO3, self.uH2O, smac_coefs)
        #
        # Use a polynomial fit of order 2 to fit relation between surface reflectance and TOA reflectance
        poly_coefs = np.polyfit(r_toa, r_surf_SMAC, 2, full=True)

        # Read image band
        Bands_toa = np.float32(array_in)
        #     # Apply fitted relation to convert TOA reflectance to surface reflectance
        surf_ref = poly_coefs[0][2] + poly_coefs[0][1] * Bands_toa + poly_coefs[0][0] * Bands_toa ** 2
        mask = (Bands_toa <= 0)
        surf_ref[mask] = 0

        log.debug('2nd Polynomial Coefs / Residual for band %s: %f %f %f %f',
            band, poly_coefs[0][2], poly_coefs[0][1], poly_coefs[0][0], poly_coefs[1][0])

        return surf_ref

    def preprocess(self, product: S2L_Product):

        log.debug("SMAC Correction")

        mtl = product.mtl

        extent = self._mgrs.get_corners(product.mgrs, out_epsg=4326)
        # # ----------------------------------------------------------------------------------
        # # Get Sensing Time
        # # ----------------------------------------------------------------------------------

        obs = str(mtl.observation_date) + 'T' + str(mtl.scene_center_time)
        obs_datetime = dt.datetime.strptime(obs, '%Y-%m-%dT%H:%M:%S.%fZ')

        # # ----------------------------------------------------------------------------------
        # # Get CAMS Data corresponding to Extent and observation data time
        # # ----------------------------------------------------------------------------------

        ecmwf_data = ECMWF_Product(cams_config=get_cams_configuration(), observation_datetime=obs_datetime)
        if ecmwf_data.is_valid:
            # Process each corner in the scene and set atmospheric parameter with cams_data
            v_ctwv = np.empty((4, 1))
            v_gtc03 = np.empty((4, 1))
            v_msl = np.empty((4, 1))
            v_aot = np.empty((4, 1))

            lon_sc = 0
            lat_sc = 0
            for index in range(4):
                lon_sc = lon_sc + (extent[2 * index]) * 0.25
                lat_sc = lat_sc + (extent[2 * index + 1]) * 0.25
                lon = extent[2 * index]
                lat = extent[2 * index + 1]
                atmo = ATMO_parameter(ecmwf_data)
                atmo.project(lat, lon)
                v_ctwv[index] = atmo.getTotalColumnWaterVapor()
                v_gtc03[index] = atmo.getTotalOzone()
                v_msl[index] = atmo.getAirPressure()
                v_aot[index] = atmo.aod550

            # Least square adjustment to get atmo parameter at the scene center
            # location (or any other points in the scene)
            # Total Column Water Vapor
            c1, c2, c3 = ATMO_parameter.compute_model(extent, v_ctwv)
            estimate_ctwv = c1 * lon_sc + c2 * lat_sc + c3

            # Total Ozone
            c1, c2, c3 = ATMO_parameter.compute_model(extent, v_gtc03)
            estimate_gtc03 = c1 * lon_sc + c2 * lat_sc + c3

            # Air pressure
            c1, c2, c3 = ATMO_parameter.compute_model(extent, v_msl)
            estimate_msl = c1 * lon_sc + c2 * lat_sc + c3

            # Total Column Water Vapor
            c1, c2, c3 = ATMO_parameter.compute_model(extent, v_aot)
            estimate_aot = c1 * lon_sc + c2 * lat_sc + c3

            self.uH2O = estimate_ctwv[0]  # Water Vapor content - unit: g.cm-2
            self.uO3 = estimate_gtc03[0]  # Ozone content - unit: unit: cm , 0.3 cm= 300 Dobson Units
            self.pressure = estimate_msl[0]  # Pressure - unit: hpa
            self.taup550 = estimate_aot[0]  # taup550 - unit: unitless

            log.info(" Results : ")
            log.info("Estimate Total colum water vapor: %s", estimate_ctwv)
            log.info("Estimate Ozone content (cm-atm) : %s", estimate_gtc03)
            log.info("Estimate Pression (hpa)         : %s", estimate_msl)
            log.info("Estimate Aot 550 nm             : %s", estimate_aot)

    def process(self, product: S2L_Product, image: S2L_ImageFile, band: str) -> S2L_ImageFile:
        log.info('Start')

        # SMAC correction
        array_in = image.array
        array_out = self.smac_correction(product, array_in, band)
        out_image = image.duplicate(self.output_file(product, band), array_out)
        if self.generate_intermediate_products:
            image.write(creation_options=['COMPRESS=LZW'])
        
        log.info('End')

        return out_image

    def postprocess(self, product: S2L_Product):
        """Set QI params

        Args:
            product (S2L_Product): product to post process
        """

        product.metadata.qi["AC_PROCESSOR"] = "SMAC"
        # TODO: put config param in self ?
        product.metadata.qi["GRANULE_MEAN_WV"] = self.uH2O
        product.metadata.qi["OZONE_VALUE"] = self.uO3
        product.metadata.qi["PRESSURE"] = self.pressure
        product.metadata.qi["GRANULE_MEAN_AOT"] = self.taup550
