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

"""Common function for landsat readers"""
import os

import numpy as np
from fmask import landsatangles
from osgeo import gdal
from rios import fileinfo


def downsample_coarse_image(image_path: str, out_dir: str, ds_factor: int) -> str:
    """Downsample coarse image in file named tie_points_coarseResImage.tif with factor * 30

    Args:
        image (str): input image path
        out_dir (str): image output dir
        ds_factor (int): downsample factor

    Returns:
        str: output image path
    """
    if not os.path.exists(out_dir):
        os.makedirs(out_dir)
    coarse_res_image = os.path.join(out_dir, 'tie_points_coarseResImage.tif')
    gdal.Translate(coarse_res_image, image_path, xRes=30 * ds_factor, yRes=30 * ds_factor)
    return coarse_res_image


def make_angles_image(template_img, outfile, nadir_line, extent_sun_angles, sat_azimuth):
    """
    Make a single output image file of the sun and satellite angles for every
    pixel in the template image.

    """
    img_info = fileinfo.ImageInfo(template_img)

    infiles = landsatangles.applier.FilenameAssociations()
    outfiles = landsatangles.applier.FilenameAssociations()
    otherargs = landsatangles.applier.OtherInputs()
    controls = landsatangles.applier.ApplierControls()

    infiles.img = template_img
    outfiles.angles = outfile

    ctr_lat = landsatangles.getCtrLatLong(img_info)[0]
    otherargs.R = landsatangles.localRadius(ctr_lat)
    otherargs.nadirLine = nadir_line
    otherargs.xMin = img_info.xMin
    otherargs.xMax = img_info.xMax
    otherargs.yMin = img_info.yMin
    otherargs.yMax = img_info.yMax
    otherargs.extentSunAngles = extent_sun_angles
    otherargs.satAltitude = 705000  # Landsat nominal altitude in metres
    otherargs.satAzimuth = sat_azimuth
    otherargs.radianScale = 100 * 180 / np.pi  # Store pixel values in degrees and scale factor of 100
    controls.setStatsIgnore(500)
    controls.setCalcStats(False)
    controls.setOutputDriverName('GTiff')

    landsatangles.applier.apply(landsatangles.makeAngles, infiles, outfiles, otherargs, controls=controls)
