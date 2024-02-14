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

import logging

import numpy as np

log = logging.getLogger("Sen2Like")


class ATMO_parameter:
    """
    Related to Atmospheric properties of a given geolocation
    Used cams_data as property
    Return with getValues, the coefficient
    Properties of this object should be set dynamically
    Depending on the content of the input CAMS File.
    """

    def __init__(self, cams_data):
        self.ecmwf_data = cams_data
        self.tcwv = None
        self.gtco3 = None
        self.msl = None
        self.aod550 = None

    def getTotalColumnWaterVapor(self):
        result = np.multiply(self.tcwv, 0.1)
        log.debug("Water Vapor Column, tcwv (g.cm-2): %s" % str(result))
        return result

    def getTotalOzone(self):
        result = np.divide(np.divide(self.gtco3, 2.14151869e-05), 1000.0)
        log.debug("Ozone concentration (cm-atm): %s" % str(result))
        return result

    def getAirPressure(self):
        result = np.multiply(self.msl, 0.01)
        log.debug("Air Pressure, msl (hPa): %s" % str(result))
        return result

    def project(self, latitude, longitude):
        """
        #Set atmospheric parameters for the given lat/lon/cams_data
        #As per dynamic properties of object
        :return:
        """
        longitude = longitude if longitude > 0 else 360 + longitude

        lon_array = self.ecmwf_data.longitude
        lat_array = self.ecmwf_data.latitude

        # Find in the lon_array / lat_array the index interval
        # Including lon_ul and lat_ul
        a_lon = np.where((lon_array < longitude))[0][-1]
        if longitude > lon_array.max():
            # lon is between 359.6 and 0 ...
            b_lon = 0
        else:
            b_lon = np.where((lon_array >= longitude))[0][0]

        a_lat = np.where((lat_array < latitude))[0][0]
        b_lat = np.where((lat_array >= latitude))[0][-1]

        # Compute geo extent around the point :
        # => extent definition : LR,LL,UL,UR
        extent = [lon_array[a_lon], lat_array[a_lat],
                  lon_array[b_lon], lat_array[a_lat],
                  lon_array[b_lon], lat_array[b_lat],
                  lon_array[a_lon], lat_array[b_lat]]

        extent_index = [a_lon, a_lat,
                        b_lon, a_lat,
                        b_lon, b_lat,
                        a_lon, b_lat]

        log.info(' - Selected vertex : ')
        log.info('LL (px,ln) / (lon,lat) : (%s, %s) / (%s dd , %s dd)' % (
            str(extent_index[0]), str(extent_index[1]), str(extent[0]), str(extent[1])))
        log.info('LR (px,ln) / (lon,lat) : (%s, %s) / (%s dd , %s dd)' % (
            str(extent_index[2]), str(extent_index[3]), str(extent[2]), str(extent[3])))
        log.info('UR (px,ln) / (lon,lat) : (%s, %s) / (%s dd , %s dd)' % (
            str(extent_index[4]), str(extent_index[5]), str(extent[4]), str(extent[5])))
        log.info('UL (px,ln) / (lon,lat) : (%s, %s) / (%s dd , %s dd)' % (
            str(extent_index[6]), str(extent_index[7]), str(extent[6]), str(extent[7])))

        # TIE Point grid defined - compute linear transformation
        # to estimate value at the lat/lon location
        # origin : extent_ul[0], extent_ul[1]
        delta_lon = 0.4  # extent[4] - extent[6]  # UR - UL
        delta_lat = -0.4  # extent[1] - extent[7]  # LL - UL

        lambda_lat = latitude - extent[7]
        lambda_lon = longitude - extent[6]

        beta_longitude = lambda_lon / delta_lon
        beta_latitude = lambda_lat / delta_lat

        # Processing of all keys
        for key in self.ecmwf_data.mandatory_attributes:
            M = getattr(self.ecmwf_data, key)
            v = self.linear_estimate(M,
                                     beta_latitude,
                                     beta_longitude,
                                     extent_index)
            setattr(self, key, v)

    @staticmethod
    def linear_estimate(A, beta_latitude, beta_longitude, extent_index):
        """
        Compute atmospheric value for this point
        Retrieve value associated with the extent

        :param A: Matrix as input (tcwv,...)
        :param beta_latitude: Weight coordinate of the point (latitude)
        :param beta_longitude: Weight coordinate of the point (longitude)
        :param extent_index: Geographical coordinates of the Matrix
                             in the order LL,LR,UR,UL for twin (longitude,latitude)
        :return: the estimated value at the relative location
                given by beta_latitude / beta longitude

        """

        v1 = (A[extent_index[7], extent_index[6]])  # UL
        v2 = (A[extent_index[5], extent_index[4]])  # UR
        v3 = (A[extent_index[1], extent_index[0]])  # LL

        estimate_v = v1 + (v2 - v1) * beta_longitude + (v3 - v1) * beta_latitude
        return estimate_v

    @classmethod
    def compute_model(cls, extent, v):
        """
        :param extent: The list of latitudes and longitudes
        :param v:  The list of values
        :return:  Linear transform parameters

        A.C = V with C = [c0 c1 c2]
        """
        A = np.empty((4, 3))
        for i in range(0, 4, 1):
            A[i, :] = ([extent[2 * i], extent[2 * i + 1], 1])

        return np.linalg.lstsq(A, v, rcond=None)[0]
