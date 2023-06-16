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

"""module to manage reference image"""

import json
import logging
import os

from core.image_file import S2L_ImageFile
from grids.mgrs_framing import resample

logger = logging.getLogger("Sen2Like")


def get_ref_image(ref_image_path, references_map_file, tile=None):
    ref_image = None

    if ref_image_path:
        ref_image = ref_image_path
    elif references_map_file and tile:
        if os.path.isfile(references_map_file):
            # load dataset
            with open(references_map_file) as json_file:
                references_map = json.load(json_file)
            ref_image = references_map.get(tile)
        else:
            logger.warning("The reference path %s doesn't exist. So it is considered as None.", references_map_file)

    return ref_image


def get_resampled_ref_image(image: S2L_ImageFile, ref_image_path: str) -> S2L_ImageFile:
    """Get reference image file to use for matching as `S2L_ImageFile`
    Try to adapt resolution, changing end of reference filename in the `S2L_ImageFile` after resampling if needed

    Args:
        image (S2L_ImageFile): image for which we look for ref image
        ref_image_path (str): path to the reference image to load

    Returns:
        S2L_ImageFile: reference image denoted by 'ref_image_path'
        or a new one resample to 'image' X resolution if resolutions differ
    """

    # try to adapt resolution, changing end of reference filename
    if not ref_image_path or not os.path.exists(ref_image_path):
        return None

    # open image ref
    ref_image = S2L_ImageFile(ref_image_path)

    # if ref image resolution does not fit
    if ref_image.xRes != image.xRes:
        # new ref image filepath
        ref_image_no_ext = os.path.splitext(ref_image_path)[0]
        if ref_image_no_ext.endswith(f"_{int(ref_image.xRes)}m"):
            ref_image_no_ext = ref_image_no_ext[:-len(f"_{int(ref_image.xRes)}m")]
        ref_image_path = ref_image_no_ext + f"_{int(image.xRes)}m.TIF"

        # compute (resample), or load if exists
        if not os.path.exists(ref_image_path):
            logger.info("Resampling of the reference image")
            # compute
            ref_image = resample(ref_image, image.xRes, ref_image_path)
            # write for reuse
            ref_image.write(DCmode=True, creation_options=['COMPRESS=LZW'])
        else:
            # or load if exists
            logger.info("Change reference image to: %s", ref_image_path)
            ref_image = S2L_ImageFile(ref_image_path)

    return ref_image