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

"""Geometry correction processing block module"""

import logging
import os

import numpy as np
from core.image_file import S2L_ImageFile
from core.mask_util import MaskInfo
from core.products.product import S2L_Product
from core.reference_image import get_resampled_ref_image
from grids import mgrs_framing
from klt import KLTMatcher, KTLResult
from s2l_processes.S2L_Process import S2L_Process

log = logging.getLogger("Sen2Like")


def reframe_mask(
    product: S2L_Product, product_mask_filename_attr: str, output_filename: str, **kwargs
) -> S2L_ImageFile:
    """Reframe a mask of a product and set product reader mask attr to the reframed mask

    Args:
        product (S2L_Product): product having the mask
        product_mask_filename_attr (str): mask file name attr in the product reader
        output_filename (str): filename for the reframed mask
        **kwargs: any args for 'S2L_ImageFile.write' except 'creation_options'
    Returns:
        S2L_ImageFile : mask image
    """
    filepath_out = os.path.join(product.working_dir, output_filename)

    mask_file_path = getattr(product, product_mask_filename_attr, None)
    image = S2L_ImageFile(mask_file_path)

    out_image = mgrs_framing.reframe(
        image, product.mgrs, filepath_out, product.dx, product.dy, order=0
    )

    out_image.write(creation_options=["COMPRESS=LZW"], **kwargs)

    setattr(product, product_mask_filename_attr, filepath_out)

    return out_image


class S2L_Geometry(S2L_Process):
    """
    Class to reframe a product in a MGRS geometry
    and correct the product geometry based on reference product
    """

    def __init__(
        self,
        klt_matcher: KLTMatcher,
        force_geometric_correction: bool,
        do_matching_correction: bool,
        reference_band: str,
        generate_intermediate_products: bool,
    ):
        """Constructor

        Args:
            klt_matcher (KLTMatcher): KLT matcher component
            force_geometric_correction (bool): force geometric correction for refined products
            do_matching_correction (bool): compute or not dx/dy.
                If False, the consequence is that only reframing will be done, no correction at all
            reference_band (str): the reference band for matching
            generate_intermediate_products (bool): flag to generate or not intermediate image products.
        """
        super().__init__(generate_intermediate_products)
        self._force_geometric_correction = force_geometric_correction
        self._do_matching_correction = do_matching_correction
        self._reference_band = reference_band
        self._output_file = None
        # avoid process related product when process is called from preprocess for "main" product
        self._process_related_product = False
        self._klt_results = []
        self._klt_matcher = klt_matcher

    def preprocess(self, product: S2L_Product):
        """
        Compute product dx/dy deviation and reframe product aux data files considering deviation in the MGRS tile.
        dx/dy are computed with klt module.
        dx/dy are computed only if doMatchingCorrection conf param is True, otherwise, 0 is considered.
        Angle file reframe in the MGRS tile without considering dx/dy because of very low resolution.
        If the product have a related product, also preprocess it.
        Computed dx/dy will be applied to product image bands during process.
        dx/dy are set in the product.

        Args:
            product (S2L_Product): product to preprocess
        """

        # No geometric correction for refined products
        if product.mtl.is_refined:
            if self._force_geometric_correction:
                log.info(
                    "Product %s is refined but geometric correction is forced.",
                    product.name
                )
            else:
                log.info("Product %s is refined: no additional geometric correction.", product.name)
                # have a dummy klt result for COREGISTRATION_BEFORE_CORRECTION computation
                self._klt_results.append(KTLResult([0], [0], 0))
                # attempt to preprocess related, it could be not refined
                self._preprocess_related(product)
                return

        # reframe angle file and validity mask, reframed validity mask is needed for matching
        self._pre_reframe_aux_files(product)

        # Matching for dx/dy correction, goal is to compute and feed dx, dy in product
        self._do_matching(product)

        # Reframe aux data with computed dx/dy,
        # but not angle file because it have a very low resolution
        self._post_reframe_aux_files(product)

        # attempt to preprocess related
        self._preprocess_related(product)

        self._set_qi_information(product)

    def _pre_reframe_aux_files(self, product: S2L_Product):
        """Reframe product angle file and validity mask to the product MGRS tile

        Args:
            product (S2L_Product): product having file to reframe
        """
        # Reframe angles, only once without correction because very low resolution
        if product.reframe_angle_file:
            log.info("MGRS reframe angle file of %s", product.name)
            filepath_out = os.path.join(product.working_dir, "tie_points_REFRAMED.TIF")
            mgrs_framing.reframe_multiband(
                product.angles_file, product.mgrs, filepath_out, product.dx, product.dy, order=0
            )
            # update product angles_images
            product.angles_file = filepath_out

        # Reframe validity mask only because needed for KLT
        if product.mask_filename:
            log.info("MGRS reframe mask file of %s", product.name)
            reframe_mask(product, "mask_filename", "valid_pixel_mask_REFRAMED.TIF")

    def _post_reframe_aux_files(self, product: S2L_Product):
        """Reframe validity mask, no data mask and ndvi file if they exist by applying product dx/dy

        Args:
            product (S2L_Product): product having aux data file to reframe
        """
        valid_mask: S2L_ImageFile|None = None
        no_data_mask: S2L_ImageFile|None = None
        if product.mask_filename:
            log.info("MGRS Reframe mask of product %s", product.name)
            valid_mask = reframe_mask(
                product,
                "mask_filename",
                "valid_pixel_mask_REFRAMED_GEOM_CORRECTED.TIF"
            )

        if product.nodata_mask_filename:
            log.info("MGRS Reframe no data mask of product %s", product.name)
            no_data_mask = reframe_mask(
                product, "nodata_mask_filename", "nodata__mask_REFRAMED_GEOM_CORRECTED.TIF"
            )

        if product.ndvi_filename is not None:
            log.info("MGRS Reframe NDVI of product %s", product.name)
            reframe_mask(product, "ndvi_filename", "ndvi_REFRAMED_GEOM_CORRECTED.TIF", DCmode=True)

        if valid_mask and no_data_mask:
            log.info("Recompute mask info")
            log.info("old: %s",product.mask_info)

            product.mask_info = MaskInfo(
                valid_mask.array.size,
                np.count_nonzero(valid_mask.array),
                no_data_mask.array.size - np.count_nonzero(no_data_mask.array)
            )
            log.info("new: %s",product.mask_info)
        
    def _set_qi_information(self, product):
        """Set COREGISTRATION_BEFORE_CORRECTION, INPUT_RMSE_X, INPUT_RMSE_Y in QI report.
        If the processed product have a related product, the information is set for the product and its related one
        """
        # self._klt_results have been filled by co registration for each product (main and related)
        # so we can compute COREGISTRATION_BEFORE_CORRECTION QI field
        if self._klt_results:
            stats = {"dist_means": [], "rmse_x": [], "rmse_y": []}

            for klt_result in self._klt_results:
                dist = np.sqrt(
                    np.power(klt_result.dx_array, 2) + np.power(klt_result.dy_array, 2)
                ).flatten()
                stats["dist_means"].append(np.round(np.mean(dist), 1))

                stats["rmse_x"].append(
                    np.round(np.sqrt(np.mean(np.power(klt_result.dx_array, 2))), 1)
                )
                stats["rmse_y"].append(
                    np.round(np.sqrt(np.mean(np.power(klt_result.dy_array, 2))), 1)
                )

            self._set_formatted_qi(product, "COREGISTRATION_BEFORE_CORRECTION", stats["dist_means"])
            self._set_formatted_qi(product, "INPUT_RMSE_X", stats["rmse_x"])
            self._set_formatted_qi(product, "INPUT_RMSE_Y", stats["rmse_y"])

    def _set_formatted_qi(self, product, qi_name, qi_values):
        formatted = " ".join(f"{val:.3f}" for val in qi_values)
        product.metadata.qi.update({qi_name: formatted})

    def _preprocess_related(self, product: S2L_Product):
        """
        Preprocess related product if any.
        Set _process_related_product to True if related product

        Args:
            product (S2L_Product): product that could have related
        """
        # do the preprocess for related product if any
        if product.related_product is not None:
            log.info("Preprocess %s", product.related_product.name)
            self.preprocess(product.related_product)
            # will make related product processed band by band
            self._process_related_product = True

    def process(self, product: S2L_Product, image: S2L_ImageFile, band: str) -> S2L_ImageFile:
        """
        Reframe product image band by using product dx/dy deviation.
        If product have a related product, it is also processed with it own dx/dy.

        Args:
            product (S2L_Product): product to process
            image (S2L_ImageFile): product image to process
            band (str): band to process

        Returns:
            S2L_ImageFile: preprocess result : image reframed
        """
        # No geometric correction for refined products
        if product.mtl.is_refined:
            if self._force_geometric_correction:
                log.info(
                    "In process, product %s is refined but geometric correction is forced.",
                    product.name
                )
            else:
                log.info(
                    "In process, product %s is refined: no additional geometric correction.",
                    product.name
                )

                # attempt to process related, it could be no refined
                self._process_related(product, band)
                return image

        self._output_file = self.output_file(product, band)

        # MGRS reframing
        log.debug("Product dx / dy : %s / %s", product.dx, product.dy)
        image = self._reframe(product, image, product.dx, product.dy)

        # attempt to process related
        self._process_related(product, band)

        return image

    def _process_related(self, product: S2L_Product, band: str):
        """
        Process related product band if product have a related.
        Process only if product have been preprocessed
        because process is used in preprocess (_process_related_product flag)

        Args:
            product (S2L_Product): product that could have a related product
            band (str): product band to process
        """
        # when process is called first from preprocess, does not process the related product
        # let it to the call of preprocess for the related product
        if self._process_related_product and product.related_product is not None:
            log.info(
                "Process band %s of related product %s for %s",
                band,
                product.related_product.name,
                product.name
            )
            related_image = self.process(
                product.related_product, product.related_product.get_band_file(band), band
            )
            # set related_image IN THE RELATED_PRODUCT of product
            product.related_product.related_image_dict[band] = related_image

    def _do_matching(self, product: S2L_Product):
        """
        Compute dx/dy with KLTMatcher and set them in the product

        Args:
            product (S2L_Product): product to compute dx/dy for
        """

        if not self._do_matching_correction:
            log.warning("Matching correction is disabled")
            return

        if not product.ref_image:
            log.warning("No reference configured for matching correction, abort")
            return

        # reframe image reference band image
        image = product.get_band_file(self._reference_band)
        reframed_image = self.process(product, image, self._reference_band)

        # get ref image at the same resolution
        ref_image = get_resampled_ref_image(reframed_image, product.ref_image)
        if not ref_image:
            log.warning(
                "Cannot do matching correction, no reference image found for image %s",
                reframed_image.filepath,
            )
            return

        # open validity mask
        mask = S2L_ImageFile(product.mask_filename)

        # matching to compute product dx/dy
        # Fine resolution of correlation grid (for accurate dx dy computation)
        klt_result = self._klt_matcher.do_matching(
            product.working_dir, ref_image, reframed_image, mask.array
        )

        # save values for future correction process on bands
        product.dx = klt_result.dx_array.mean()
        product.dy = klt_result.dy_array.mean()

        # save klt result for QI computation
        self._klt_results.append(klt_result)
        log.info("Geometrical Offsets (DX/DY): %sm %sm", product.dx, product.dy)

    def _reframe(self, product: S2L_Product, image_in: S2L_ImageFile, dx=0.0, dy=0.0):
        """
        Reframe image of the given product in the product mgrs tile

        Args:
            product (S2L_Product): product for which image is reframe, used to get target mgrs tile
            image_in (S2L_ImageFile): image to reframe
            dx (float, optional): dx to apply during reframing. Defaults to 0..
            dy (float, optional): dy to apply during reframing. Defaults to 0..

        Returns:
            S2L_ImageFile: reframed image
        """
        log.info("MGRS Framing: Start...")

        # reframe on MGRS
        image_out = mgrs_framing.reframe(
            image_in,
            product.mgrs,
            self._output_file,
            dx,
            dy,
            dtype=np.float32,
            method=product.geometry_correction_strategy,
        )

        # display
        if self.generate_intermediate_products:
            image_out.write(DCmode=True)  # digital count
        log.info("MGRS Framing: End")

        return image_out
