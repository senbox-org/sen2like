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
from dataclasses import dataclass

import numpy as np

from core.image_file import S2L_ImageFile


log = logging.getLogger("Sen2Like")


@dataclass
class MaskImage:
    """Dataclass to write mask file having:
    - 'mask_array' content
    - 'mask_filename' as full name (full path) to write it
    - 'resolution' as output resolution
    - 'orig_image' is the S2_Image used to write the mask,
    it should be the orig file from witch the mask is extracted/generated.
    'orig_image' can be None, in this case, 'write' function have no effect
    """
    orig_image: S2L_ImageFile
    mask_array: np.ndarray
    mask_filename: str
    resolution: int

    def write(self):
        """Write the mask in 'mask_filename' using 'orig_image'"""
        if self.orig_image:
            mask = self.orig_image.duplicate(self.mask_filename, array=self.mask_array, res=self.resolution)
            mask.write(creation_options=['COMPRESS=LZW'])
            log.info('Written: %s', self.mask_filename)
        else:
            log.warning('Cannot write: %s, please verify it have been written', self.mask_filename)
            # this case happen in Sentinel2MTL._create_valid_mask_form_l1c_gml,
            # the mask is already created and written
            # shall we find a way to not write it and create it here ?


@dataclass
class ImageMasks:
    """'MaskImage' container for validity and no data mask
    """
    no_data_mask: MaskImage
    validity_mask: MaskImage

    def write(self):
        """Write image masks using 'MaskImage.write'"""
        self.no_data_mask.write()
        self.validity_mask.write()


@dataclass
class MaskInfo:
    """Mask information having info to compute valid and nodata pixel percentage"""
    mask_size: int
    nb_valid_pixel: int
    nb_nodata_pixel: int

    def get_valid_pixel_percentage(self) -> float:
        """get valid pixel percentage considering nodata

        Returns:
            float: valid pixel percentage
        """
        if self.nb_valid_pixel == 0:
            return self.nb_valid_pixel
        if self.mask_size == self.nb_nodata_pixel:
            return 0
        return (self.nb_valid_pixel * 100) / (self.mask_size - self.nb_nodata_pixel)

    def get_nodata_pixel_percentage(self) -> float:
        """get nodata pixel percentage

        Returns:
            float: valid pixel percentage
        """
        return (self.nb_nodata_pixel * 100) / self.mask_size
