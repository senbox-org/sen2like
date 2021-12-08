#! /usr/bin/env python
# -*- coding: utf-8 -*-
# V. Debaecker (TPZ-F) 2018

import logging
import os

import cv2
import numpy as np
from skimage.transform import resize as skit_resize
from scipy.stats import skew, kurtosis

from core import S2L_config
from core.QI_MTD.mtd import metadata
from core.image_file import S2L_ImageFile
from grids import mgrs_framing
from s2l_processes.S2L_Process import S2L_Process

log = logging.getLogger("Sen2Like")


def pointcheck_average(dx):
    return abs(dx - np.average(dx)) <= min(3 * np.std(dx), 20)


def pointcheck(x0, y0, x1, y1):
    dx = x1 - x0
    dy = y1 - y0

    while True:
        valid_indices = np.where(pointcheck_average(dx) & pointcheck_average(dy))
        if np.array_equal(dx[valid_indices], dx):
            break

        dx = dx[valid_indices]
        dy = dy[valid_indices]
        x0 = x0[valid_indices]
        x1 = x1[valid_indices]
        y0 = y0[valid_indices]
        y1 = y1[valid_indices]
    return x0, y0, x1, y1, dx, dy


def stretch_uint8(data, mask=None):
    if data.max() > 255:
        if mask is not None:
            data_tmp = data
            data_tmp[mask == 0] = 0
            _max = data_tmp.max()
        else:
            _max = data.max()
        data = data * 255. / _max
    data = np.uint8(data.clip(min=0, max=255))
    return data


def extract_features(data, ddepth=cv2.CV_8U, ksize=5, mask=None):
    # histo
    result = stretch_uint8(data, mask)
    # sobel
    # result = cv2.Sobel(result, ddepth, 1, 1, ksize=ksize)
    result = cv2.Laplacian(result, ddepth, ksize=ksize)
    # clipping
    result = np.uint8(result.clip(min=0, max=255))
    return result


def KLT_Tracker(reference, imagedata, mask, matching_winsize=25):
    ##

    log.info("extract_features")
    imagedata = extract_features(imagedata)
    reference = extract_features(reference)

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
        return None, None, 0

    # define KLT parameters-for matching
    log.info("Using window of size {} for matching.".format(matching_winsize))
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

    logging.debug("Nb Bad Status: {}".format(len(st[st == 0])))

    p0 = p0[st]
    p1 = p1[st]

    x0 = p0[:, :, 0].ravel()
    y0 = p0[:, :, 1].ravel()
    x1 = p1[:, :, 0].ravel()
    y1 = p1[:, :, 1].ravel()

    # analyze points and remove outliers
    n_init = len(x0)
    x0, y0, x1, y1, dx, dy = pointcheck(x0, y0, x1, y1)

    return np.array(dx), np.array(dy), n_init


class S2L_GeometryKLT(S2L_Process):

    def initialize(self):
        self._output_file = None
        self._tmp_stats = {}

    def preprocess(self, product):
        # No geometric correction for refined products
        if product.mtl.is_refined:
            if S2L_config.config.getboolean('force_geometric_correction'):
                log.info("Product is refined but geometric correction is forced.")
            else:
                log.info("Product is refined: no additional geometric correction.")
                return

        # reinit dx/dy
        S2L_config.config.set('dx', 0)
        S2L_config.config.set('dy', 0)

        if product.sensor != 'S2':
            # Reframe angles and masks
            filepath_out = os.path.join(S2L_config.config.get('wd'), product.name, 'tie_points_REFRAMED.TIF')
            mgrs_framing.reframeMulti(product.mtl.angles_file, product.mtl.mgrs, filepath_out,
                                      S2L_config.config.getfloat('dx'),
                                      S2L_config.config.getfloat('dy'), order=0)
            product.mtl.angles_file = filepath_out

        # Reframe mask
        if product.mtl.mask_filename:
            filepath_out = os.path.join(S2L_config.config.get('wd'), product.name, 'valid_pixel_mask_REFRAMED.TIF')
            image = S2L_ImageFile(product.mtl.mask_filename)
            imageout = mgrs_framing.reframe(image, product.mtl.mgrs, filepath_out, S2L_config.config.getfloat('dx'),
                                            S2L_config.config.getfloat('dy'), order=0)
            imageout.write(creation_options=['COMPRESS=LZW'])
            product.mtl.mask_filename = filepath_out

        # Reframe nodata mask
        if product.mtl.nodata_mask_filename:
            filepath_out = os.path.join(S2L_config.config.get('wd'), product.name, 'nodata_pixel_mask_REFRAMED.TIF')
            image = S2L_ImageFile(product.mtl.nodata_mask_filename)
            imageout = mgrs_framing.reframe(image, product.mtl.mgrs, filepath_out, S2L_config.config.getfloat('dx'),
                                            S2L_config.config.getfloat('dy'), order=0)
            imageout.write(creation_options=['COMPRESS=LZW'])
            product.mtl.nodata_mask_filename = filepath_out

        # Reframe NDVI
        if product.ndvi_filename is not None:
            filepath_out = os.path.join(S2L_config.config.get('wd'), product.name, 'ndvi_REFRAMED.TIF')
            image = S2L_ImageFile(product.ndvi_filename)
            imageout = mgrs_framing.reframe(image, product.mtl.mgrs, filepath_out, S2L_config.config.getfloat('dx'),
                                            S2L_config.config.getfloat('dy'), order=0)
            imageout.write(creation_options=['COMPRESS=LZW'], DCmode=True)
            product.ndvi_filename = filepath_out

        # Matching for dx/dy correction?
        band = S2L_config.config.get('reference_band', 'B04')
        if S2L_config.config.getboolean('doMatchingCorrection') and S2L_config.config.get('refImage'):
            S2L_config.config.set('freeze_dx_dy', False)
            image = product.get_band_file(band)
            self.process(product, image, band)
            # goal is to feed dx, dy in config
            S2L_config.config.set('freeze_dx_dy', True)
            metadata.qi.update({'COREGISTRATION_BEFORE_CORRECTION': self._tmp_stats.get('MEAN')})

    def process(self, product, image, band):
        # No geometric correction for refined products
        if product.mtl.is_refined:
            if S2L_config.config.getboolean('force_geometric_correction'):
                log.info("Product is refined but geometric correction is forced.")
            else:
                log.info("Product is refined: no additional geometric correction.")
                return image

        wd = os.path.join(S2L_config.config.get('wd'), product.name)
        self._output_file = self.output_file(product, band)
        self._tmp_stats = {}

        log.info('Start')

        # MGRS reframing for Landsat8
        if product.sensor in ('L8', 'L9'):
            log.debug('{} {}'.format(S2L_config.config.getfloat('dx'), S2L_config.config.getfloat('dy')))
            image = self._reframe(product, image, S2L_config.config.getfloat('dx'), S2L_config.config.getfloat('dy'))

        # Resampling to 30m for S2 (HLS)
        elif product.sensor == 'S2':
            # refine geometry
            # if config.getfloat('dx') > 0.3 or config.getfloat('dy') > 0.3:
            log.debug("{} {}".format(S2L_config.config.getfloat('dx'), S2L_config.config.getfloat('dy')))
            image = self._reframe(product, image, S2L_config.config.getfloat('dx'),
                                  S2L_config.config.getfloat('dy'))

        # matching for having QA stats
        if S2L_config.config.get('refImage'):

            # try to adapt resolution, changing end of reference filename
            refImage_path = S2L_config.config.get('refImage')
            if not os.path.exists(refImage_path):
                return image

            # open image ref
            imageref = S2L_ImageFile(refImage_path)

            # if refImage resolution does not fit
            if imageref.xRes != image.xRes:
                # new refImage filepath
                refImage_noext = os.path.splitext(refImage_path)[0]
                if refImage_noext.endswith(f"_{int(imageref.xRes)}m"):
                    refImage_noext = refImage_noext[:-len(f"_{int(imageref.xRes)}m")]
                refImage_path = refImage_noext + f"_{int(image.xRes)}m.TIF"

                # compute (resample), or load if exists
                if not os.path.exists(refImage_path):
                    log.info("Resampling of the reference image")
                    # compute
                    imageref = mgrs_framing.resample(imageref, image.xRes, refImage_path)
                    # write for reuse
                    imageref.write(DCmode=True, creation_options=['COMPRESS=LZW'])
                else:
                    # or load if exists
                    log.info("Change reference image to:" + refImage_path)
                    imageref = S2L_ImageFile(refImage_path)

            # open mask
            mask = S2L_ImageFile(product.mtl.mask_filename)
            if S2L_config.config.getboolean('freeze_dx_dy'):
                # do Geometry Assessment only if required
                assess_geometry_bands = S2L_config.config.get('doAssessGeometry', default='').split(',')
                if product.sensor != 'S2':
                    assess_geometry_bands = [product.reverse_bands_mapping.get(band) for band in assess_geometry_bands]
                if assess_geometry_bands and band in assess_geometry_bands:
                    log.info("Geometry assessment for band %s" % band)
                    # Coarse resolution of correlation grid (only for stats)
                    self._matching(imageref, image, wd, mask)

            else:
                # Fine resolution of correlation grid (for accurate dx dy computation)
                dx, dy = self._matching(imageref, image, wd, mask)
                # save values for correction on bands
                S2L_config.config.set('dx', dx)
                S2L_config.config.set('dy', dy)
                log.info("Geometrical Offsets (DX/DY): {}m {}m".format(S2L_config.config.getfloat('dx'),
                                                                       S2L_config.config.getfloat('dy')))

            # Append bands name to keys
            for key, item in self._tmp_stats.items():
                if S2L_config.config.get('reference_band') != band:
                    self._tmp_stats[key + '_{}'.format(band)] = self._tmp_stats.pop(key)
            metadata.qi.update(self._tmp_stats)

        log.info('End')
        return image

    def _reframe(self, product, imagein, dx=0., dy=0.):
        log.info('MGRS Framing: Start...')

        # reframe on MGRS
        imageout = mgrs_framing.reframe(imagein, product.mtl.mgrs, self._output_file, dx, dy, dtype=np.float32)

        # display
        if S2L_config.config.getboolean('generate_intermediate_products'):
            imageout.write(DCmode=True)  # digital count
        log.info('MGRS Framing: End')

        return imageout

    def _resample(self, imagein):

        # display
        log.info('Resampling to 30m: Start...')

        # resampling
        imageout = mgrs_framing.resample(imagein, 30, self._output_file)

        # display
        if S2L_config.config.getboolean('generate_intermediate_products'):
            imageout.write(DCmode=True)  # digital count
        log.info('Resampling to 30m: End')

        return imageout

    def _matching(self, imageref, imagesec, wd, mask):

        log.info('Start matching')

        # do matching with KLT
        dx, dy, Ninit = KLT_Tracker(imageref.array, imagesec.array, mask.array)

        if Ninit == 0:
            log.error("Not points for matching")
            return 0, 0

        dx = dx * imageref.xRes
        dy = dy * (- imageref.yRes)
        log.debug("KLT Nb Points (init/final): {} / {}".format(Ninit, len(dx)))
        log.debug("KLT (avgx, avgy): {}m {}m".format(dx.mean(), dy.mean()))

        dist = np.sqrt(np.power(dx, 2) + np.power(dy, 2)).flatten()
        self._tmp_stats.update({'SKEW': np.round(skew(dist, axis=None), 1),
                                'KURTOSIS': np.round(kurtosis(dist, axis=None), 1),
                                'MEAN': np.round(np.mean(dist), 1),
                                'STD': np.round(np.std(dist), 1),
                                'RMSE': np.round(np.sqrt(np.mean(np.power(dist, 2))), 1),
                                'NB_OF_POINTS': len(dx)})

        # write results in csv
        csvfile = os.path.join(wd, "correl_res.txt")
        log.debug(csvfile)
        if not os.path.exists(csvfile):
            # write header
            titles = "refImg secImg total_valid_pixel sample_pixel confidence_th min_x max_x " \
                     "median_x mean_x std_x min_y max_y median_y mean_y std_y"
            with open(csvfile, 'w') as o:
                o.write(titles + "\n")
        # write values
        values = [imageref.filename, imagesec.filename, Ninit, len(dx), -1]
        values += [dy.min(), dy.max(), np.median(dy), dy.mean(), np.std(dy)]
        values += [dx.min(), dx.max(), np.median(dx), dx.mean(), np.std(dx)]
        text = " ".join([str(x) for x in values])
        with open(csvfile, 'a') as o:
            o.write(text + "\n")

        # end
        log.info('End matching')

        return dx.mean(), dy.mean()
