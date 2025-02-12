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

"""
KLT module
"""
import logging
import os
from dataclasses import dataclass, field

import cv2
import numpy as np
from pandas import DataFrame
from skimage.transform import resize as skit_resize

from core.image_file import S2L_ImageFile

log = logging.getLogger("Sen2Like")

def default_np() -> np.ndarray:
    return np.zeros([1, 1], float)


@dataclass
class KTLResult():
    """
    Class to store KLT matching result
    Default init for result with no matching point
    to ease it usage.
    """
    dx_array: np.ndarray = field(default_factory=default_np)
    dy_array: np.ndarray = field(default_factory=default_np)
    nb_matching_point: int = 0


class KLTMatcher:
    """_summary_
    """
    def _pointcheck_average(self, dx):
        return abs(dx - np.average(dx)) <= min(3 * np.std(dx), 20)

    def _pointcheck(self, x0, y0, x1, y1):
        dx = x1 - x0
        dy = y1 - y0

        while True:
            valid_indices = np.where(self._pointcheck_average(dx) & self._pointcheck_average(dy))
            if np.array_equal(dx[valid_indices], dx):
                break

            dx = dx[valid_indices]
            dy = dy[valid_indices]
            x0 = x0[valid_indices]
            x1 = x1[valid_indices]
            y0 = y0[valid_indices]
            y1 = y1[valid_indices]
        return x0, y0, x1, y1, dx, dy

    def _extract_features(self, data, ddepth=cv2.CV_8U, ksize=5):
        """Apply Laplacian operator to enhance contours in the image

        Args:
            data (ndarray): image to enhance
            ddepth (int, optional): Desired depth of the destination image. Defaults to cv2.CV_8U (0).
            ksize (int, optional): Aperture size used to compute the second-derivative filters. Defaults to 5.

        Returns:
            ndarray: Laplacian result as uint8
        """
        result = cv2.Laplacian(data, ddepth, ksize=ksize)
        # clipping
        result = np.uint8(result.clip(min=0, max=255))
        return result

    def do_matching(self, working_dir:str, ref_image: S2L_ImageFile, image: S2L_ImageFile, mask, matching_winsize=25, assessment=False) -> KTLResult:
        """Process to KLT matching, then compute dx/dy.
        Write some results stats in `working_dir/correl_res.txt`

        Args:
            working_dir (str): where to write result
            ref_image (S2L_ImageFile): reference image used for matching
            image (S2L_ImageFile): image to match
            mask (ndarray): mask to use during matching
            matching_winsize (int, optional): _description_. Defaults to 25.
            assessment: (bool, optional): flag to indicate if matching is done for assessment or not. 
                If not, then a file KLT.csv is written in the working dir and it contains KLT matching dataframe results.
                Defaults to False
        Returns:
            KTLResult: matching result
        """
        log.info('Start matching')

        log.info("extract_features")
        imagedata = self._extract_features(image.array)
        reference = self._extract_features(ref_image.array)

        # check mask shape
        if mask.shape != imagedata.shape:
            log.info("resize mask")
            mask = skit_resize(mask.clip(min=-1.0, max=1.0), imagedata.shape, order=0, preserve_range=True).astype(
                np.uint8)

        # compute the initial point set
        # goodFeaturesToTrack input parameters
        feature_params = dict(maxCorners=20000, qualityLevel=0.1,
                            minDistance=10, blockSize=15)
        # goodFeaturesToTrack corner extraction-ShiThomasi Feature Detector
        log.info("goodFeaturesToTrack")
        p0 = cv2.goodFeaturesToTrack(
            reference, mask=mask, **feature_params)
        if p0 is None:
            log.error("No features extracted")
            return KTLResult()

        # define KLT parameters-for matching
        log.info("Using window of size %s for matching.", matching_winsize)
        # LSM input parameters - termination criteria for corner estimation/stopping criteria
        lk_params = dict(winSize=(matching_winsize, matching_winsize),
                        maxLevel=1,
                        criteria=(cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT, 30, 0.03))

        p1, st, __ = cv2.calcOpticalFlowPyrLK(reference, imagedata, p0, None,
                                            **lk_params)  # LSM image matching- KLT tracker

        # Backward-check
        back_threshold = 0.01
        p0r, st, __ = cv2.calcOpticalFlowPyrLK(imagedata, reference, p1, None,
                                            **lk_params)  # LSM image matching- KLT tracker

        d = abs(p0 - p0r).reshape(-1, 2).max(-1)
        st = d < back_threshold

        logging.debug("Nb Bad Status: %s", len(st[st == 0]))

        p0 = p0[st]
        p1 = p1[st]

        x0 = p0[:, :, 0].ravel()
        y0 = p0[:, :, 1].ravel()
        x1 = p1[:, :, 0].ravel()
        y1 = p1[:, :, 1].ravel()

        # analyze points and remove outliers
        nb_matching_point = len(x0)
        x0, y0, x1, y1, dx, dy = self._pointcheck(x0, y0, x1, y1)

        if nb_matching_point == 0:
            log.error("Not points for matching")
            return KTLResult()

        # Mainly for PRISMA
        # Save KLT result in workir folder as KLT.csv in order to allow
        # mgrs reframing with polynomial strategy to have inputs to compute
        # transformation. It could also be used for other transformation.
        if not assessment:
            data_frame = DataFrame.from_dict(
                {"x0": x0, "y0": y0, "dx": dx, "dy": dy}
            )
            data_frame.sort_values(by=["x0", "y0"], inplace=True)
            data_frame.to_csv(os.path.join(working_dir, "KLT.csv"), sep=";", index=False)
        # End for PRISMA

        dx_res = np.array(dx) * ref_image.xRes
        dy_res = np.array(dy) * (- ref_image.yRes)

        log.debug("KLT Nb Points (init/final): %s / %s", nb_matching_point, len(dx_res))
        log.debug("KLT (avgx, avgy): %sm %sm", dx_res.mean(), dy_res.mean())

        result = KTLResult(dx_res, dy_res, nb_matching_point)

        self._write_results(result, working_dir, image.filename, ref_image.filename)

        log.info('End matching')

        return result

    def _write_results(self, klt_result: KTLResult, working_dir: str, image_filename: str, image_ref_filename: str):

        dx = klt_result.dx_array
        dy = klt_result.dy_array

        # write results in csv
        csvfile = os.path.join(working_dir, "correl_res.txt")
        log.debug(csvfile)
        if not os.path.exists(csvfile):
            # write header
            titles = "refImg secImg total_valid_pixel sample_pixel confidence_th min_x max_x " \
                     "median_x mean_x std_x min_y max_y median_y mean_y std_y"
            with open(csvfile, 'w') as o:
                o.write(titles + "\n")
        # write values
        values = [image_ref_filename, image_filename,
                  klt_result.nb_matching_point, len(dx), -1]
        values += [dy.min(), dy.max(), np.median(dy), dy.mean(), np.std(dy)]
        values += [dx.min(), dx.max(), np.median(dx), dx.mean(), np.std(dx)]
        text = " ".join([str(x) for x in values])
        with open(csvfile, 'a') as o:
            o.write(text + "\n")
