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


import datetime

import numpy as np
from dateutil import tz
from pyrsr import RelativeSpectralResponse
from scipy import interpolate


def generate_aggregation_coefficients_prisma_s2(product_file):
    n_bands_s2 = 13  # Number of Sentinel-2 bands

    # Load S2A Spectral Responses file using pyrsr package
    rsr_s2a = RelativeSpectralResponse(satellite="Sentinel-2A", sensor="MSI")
    rsr_s2a_wl = rsr_s2a.rsrs_wvl

    # PRISMA number of detectors (along track dimension)
    n_detectors = 1000

    # Compute spectral aggregation coefficients (PRISMA => S2-MSI-A)
    index_start_vnir = 96
    index_stop_vnir = 162
    index_start_swir = 81
    index_stop_swir = 254
    prisma_vnir_wl = product_file["KDP_AUX/Cw_Vnir_Matrix"][:, index_start_vnir:index_stop_vnir]
    prisma_vnir_fwhm = product_file["KDP_AUX/Fwhm_Vnir_Matrix"][:, index_start_vnir:index_stop_vnir]
    prisma_swir_wl = product_file["KDP_AUX/Cw_Swir_Matrix"][:, index_start_swir:index_stop_swir]
    prisma_swir_fwhm = product_file["KDP_AUX/Fwhm_Swir_Matrix"][:, index_start_swir:index_stop_swir]

    n_bands_prisma_vnir = prisma_vnir_wl.shape[1]
    n_bands_prisma_swir = prisma_swir_wl.shape[1]

    # Compute and store the PRISMA Gaussian spectral responses for each band and detector
    # Interval of definition is +/- 10 nm around central wavelength,
    # with a step of 0.1 nm which gives an interval vector of 201 elements
    # 66 Gaussian curves (VNIR) and 173 Gaussian curves (SWIR) (PRISMA)

    # Spectral interval definition in [nm] for the PRISMA hyperspectral band
    interval = 20

    # Number of points used for Gaussian Spectral responses definitions
    n_points = 10 * interval + 1

    # Initialize and then generate PRISMA Gaussian Spectral responses (VNIR)
    g_prisma_vnir = np.zeros((n_detectors, n_bands_prisma_vnir, n_points), np.double)

    for z in range(n_bands_prisma_vnir):
        prisma_vnir_wl_arr = np.array(np.tile(np.matrix(prisma_vnir_wl[:, z]).transpose(), (1, n_points)))
        prisma_vnir_fwhm_arr = np.array(np.tile(np.matrix(prisma_vnir_fwhm[:, z]).transpose(), (1, n_points)))
        x_arr = np.array(np.tile(np.linspace(0, interval, n_points), (n_detectors, 1)))
        x_wl = x_arr + prisma_vnir_wl_arr - interval / 2.0

        if prisma_vnir_fwhm_arr.mean() == 0.0:
            continue
        else:
            # https://stackoverflow.com/questions/29950557/ignore-divide-by-0-warning-in-numpy
            with np.errstate(divide="ignore", invalid="ignore"):
                g_prisma_vnir[:, z, :] = (
                    2
                    * np.sqrt(np.log(2))
                    / np.sqrt(np.pi)
                    / prisma_vnir_fwhm_arr
                    * np.exp(-np.power((4 * np.log(2) * (x_wl - prisma_vnir_wl_arr) / prisma_vnir_fwhm_arr), 2))
                )

    # Initialize and then generate PRISMA Gaussian Spectral responses (SWIR)
    g_prisma_swir = np.zeros((n_detectors, n_bands_prisma_swir, n_points), np.double)

    for z in range(n_bands_prisma_swir):
        prisma_swir_wl_arr = np.array(np.tile(np.matrix(prisma_swir_wl[:, z]).transpose(), (1, n_points)))
        prisma_swir_fwhm_arr = np.array(np.tile(np.matrix(prisma_swir_fwhm[:, z]).transpose(), (1, n_points)))
        x_arr = np.array(np.tile(np.linspace(0, interval, n_points), (n_detectors, 1)))
        x_wl = x_arr + prisma_swir_wl_arr - interval / 2.0

        if prisma_swir_fwhm_arr.mean() == 0.0:
            continue
        else:
            # https://stackoverflow.com/questions/29950557/ignore-divide-by-0-warning-in-numpy
            with np.errstate(divide="ignore", invalid="ignore"):
                g_prisma_swir[:, z, :] = (
                    2
                    * np.sqrt(np.log(2))
                    / np.sqrt(np.pi)
                    / prisma_swir_fwhm_arr
                    * np.exp(-np.power((4 * np.log(2) * (x_wl - prisma_swir_wl_arr) / prisma_swir_fwhm_arr), 2))
                )

    # Initialize and then compute Unnormalized Spectral Weight for each PRISMA band (VNIR)
    w_prisma_vnir = np.zeros((n_detectors, n_bands_prisma_vnir, n_bands_s2), np.double)

    for z in range(n_bands_prisma_vnir):
        prisma_vnir_wl_arr = np.array(np.tile(np.matrix(prisma_vnir_wl[:, z]).transpose(), (1, n_points)))
        g_prisma_vnir_arr = g_prisma_vnir[:, z, :]
        x_arr = np.array(np.tile(np.linspace(0, interval, n_points), (n_detectors, 1)))
        x_wl = x_arr + prisma_vnir_wl_arr - interval / 2.0

        # exclude PRISMA bands with wls out of S2 spectral range
        if x_wl.min() < rsr_s2a_wl.min():
            continue

        for b, (band, rsr) in enumerate(rsr_s2a.rsrs.items()):
            # b > 9 exclude S2 SWIR bands with break
            if b > 9:
                break
            f = interpolate.interp1d(rsr_s2a_wl, rsr)
            f_s2_bk = f(x_wl)
            w_prisma_vnir[:, z, b] = (g_prisma_vnir_arr * f_s2_bk).sum(axis=1)

    # Initialize and then compute Unnormalized Spectral Weight for each PRISMA band (SWIR)
    w_prisma_swir = np.zeros((n_detectors, n_bands_prisma_swir, n_bands_s2), np.double)

    for z in range(n_bands_prisma_swir):
        prisma_swir_wl_arr = np.array(np.tile(np.matrix(prisma_swir_wl[:, z]).transpose(), (1, n_points)))
        g_prisma_swir_arr = g_prisma_swir[:, z, :]
        x_arr = np.array(np.tile(np.linspace(0, interval, 10 * interval + 1), (n_detectors, 1)))
        x_wl = x_arr + prisma_swir_wl_arr - interval / 2.0

        # exclude PRISMA bands with wls out of S2 spectral range
        if x_wl.max() > rsr_s2a_wl.max() or x_wl.min() < rsr_s2a_wl.min():
            continue

        for b, (band, rsr) in enumerate(rsr_s2a.rsrs.items()):
            # b < 10 exclude S2 VNIR bands with continue
            if b < 10:
                continue
            f = interpolate.interp1d(rsr_s2a_wl, rsr)
            f_s2_bk = f(x_wl)
            w_prisma_swir[:, z, b] = (g_prisma_swir_arr * f_s2_bk).sum(axis=1)

    # Initialize Normalized Spectral Weight for each PRISMA band (VNIR)
    p_prisma_vnir = np.zeros((n_detectors, n_bands_prisma_vnir, n_bands_s2), np.double)

    for b in range(n_bands_s2):
        # b > 9 exclude S2 SWIR bands
        if b > 9:
            break
        for x in range(n_detectors):
            p_prisma_vnir[x, :, b] = w_prisma_vnir[x, :, b] / np.nansum(w_prisma_vnir[x, :, b])

    # Initialize Normalized Spectral Weight for each PRISMA band (SWIR)
    p_prisma_swir = np.zeros((n_detectors, n_bands_prisma_swir, n_bands_s2), np.double)

    for b in range(n_bands_s2):
        # b < 10 exclude S2 VNIR bands
        if b < 10:
            continue
        for x in range(n_detectors):
            p_prisma_swir[x, :, b] = w_prisma_swir[x, :, b] / np.nansum(w_prisma_swir[x, :, b])

    return p_prisma_vnir, p_prisma_swir


def read_cube_to_radiance(product_file, cube):
    # Read ScaleFactor, Offset & Cube
    if cube == "VNIR":
        gain = np.float32(product_file.attrs.get("ScaleFactor_Vnir"))
        offset = np.float32(product_file.attrs.get("Offset_Vnir"))
        image_cube = product_file["HDFEOS/SWATHS/PRS_L1_HCO/Data Fields/VNIR_Cube"]

    elif cube == "SWIR":
        gain = np.float32(product_file.attrs.get("ScaleFactor_Swir"))
        offset = np.float32(product_file.attrs.get("Offset_Swir"))
        image_cube = product_file["HDFEOS/SWATHS/PRS_L1_HCO/Data Fields/SWIR_Cube"]

    # returns array with dims (1000, 1000, n_bands_prisma)
    image_cube_radiance = np.array(image_cube).swapaxes(1, 2)
    # rotate the 66 images by 90 deg clockwise
    image_cube_radiance = np.rot90(image_cube_radiance, k=-1)
    # convert to radiance
    image_cube_radiance = (image_cube_radiance / gain + offset).astype(np.float32)

    return image_cube_radiance


def read_cube_to_radiance_l1g(product_file, cube):
    # Read ScaleFactor, Offset & Cube
    if cube == "VNIR":
        gain = np.float32(product_file.attrs.get("ScaleFactor_Vnir"))
        offset = np.float32(product_file.attrs.get("Offset_Vnir"))
        image_cube = product_file["HDFEOS/SWATHS/PRS_L1_HCO/Data Fields/VNIR_Cube"]

    elif cube == "SWIR":
        gain = np.float32(product_file.attrs.get("ScaleFactor_Swir"))
        offset = np.float32(product_file.attrs.get("Offset_Swir"))
        image_cube = product_file["HDFEOS/SWATHS/PRS_L1_HCO/Data Fields/SWIR_Cube"]

    # returns array with dims (nl, ns, n_bands_prisma)
    image_cube_radiance = np.array(image_cube).swapaxes(1, 2)
    # rotate the 66 images by 90 deg clockwise
    # image_cube_radiance = np.rot90(image_cube_radiance, k=-1)
    # convert to radiance
    image_cube_radiance = (image_cube_radiance / gain + offset).astype(np.float32)

    return image_cube_radiance


def spectral_aggregation_prisma_s2(image_cube_radiance, p_prisma, b):
    nl = image_cube_radiance.shape[0]
    ns = image_cube_radiance.shape[1]
    n_detectors = ns

    # Initialize temporary prisma_aggreg_tmp to store PRISMA contribution for each S2 band
    prisma_aggreg_tmp = np.zeros((nl, ns), np.double)

    for x in range(n_detectors):
        prisma_indexes = p_prisma[x, :, b].nonzero()

        for prisma_index in prisma_indexes[0]:
            prisma_band = image_cube_radiance[:, x, prisma_index]
            prisma_aggreg_tmp[:, x] = prisma_band * p_prisma[x, prisma_index, b] + prisma_aggreg_tmp[:, x]

    return prisma_aggreg_tmp


def radiance_to_reflectance(radiance, esun, sza, sun_earth_distance):
    # Conversion from radiance (W.m-2.sr-1.um-1) to reflectance (unitless)
    reflectance = (1 / (esun * np.cos(np.radians(sza)))) * np.pi * radiance * sun_earth_distance**2

    return reflectance


def sun_earth_correction(t):
    # source of algorithm:
    # https://sentinels.copernicus.eu/web/sentinel/technical-guides/sentinel-2-msi/level-1c/algorithm-overview
    # Test validation:
    # Product: S2A_MSIL1C_20220714T100041_N0400_R122_T33TTG_20220714T152225.SAFE
    # <U>0.967506836831442</U>
    # sun_earth_correction(datetime.datetime.strptime("2022-07-14T10:00:41.024", '%Y-%m-%dT%H:%M:%S.%f'))
    # (0.9675068368169234, 1.016653543477379)

    t_1950 = datetime.datetime(1950, 1, 1, 12, 0).replace(tzinfo=tz.tzutc())
    e = 0.01673
    n = 0.0172
    jd_1950 = (t - t_1950).days + (t - t_1950).seconds / 86400.0

    u = 1 / (1 - e * np.cos(n * (jd_1950 - 2))) ** 2
    d = np.sqrt(1 / u)

    return u, d
