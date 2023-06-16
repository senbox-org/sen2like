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


import glob
import logging
import os
import shutil
import urllib

import pystac
import rasterio
import rasterio.warp
from pystac.extensions.eo import Band, EOExtension
from shapely.geometry import Polygon, mapping

log = logging.getLogger("Sen2Like")


def get_bbox_and_footprint(raster_uri):
    with rasterio.open(raster_uri) as ds:
        bounds = ds.bounds

        left, bottom, right, top = rasterio.warp.transform_bounds(ds.crs, "EPSG:4326", bounds.left, bounds.bottom,
                                                                  bounds.right, bounds.top)

        bbox = [left, bottom, right, top]
        footprint = Polygon([
            [left, bottom],
            [left, top],
            [right, top],
            [right, bottom]
        ])

        return bbox, mapping(footprint)


class STACWriter:
    """Writes a product as a stac item."""

    s2_bands = [
        Band.create(name="B01", description="", common_name="Coastal aerosol", center_wavelength=0.443),
        Band.create(name="B02", description="", common_name="Blue", center_wavelength=0.49),
        Band.create(name="B03", description="", common_name="Green", center_wavelength=0.56),
        Band.create(name="B04", description="", common_name="Red", center_wavelength=0.665),
        Band.create(name="B05", description="", common_name="Red Edge 1", center_wavelength=0.705),
        Band.create(name="B06", description="", common_name="Red Edge 2", center_wavelength=0.740),
        Band.create(name="B07", description="", common_name="Red Edge 3", center_wavelength=0.783),
        Band.create(name="B08", description="", common_name="NIR", center_wavelength=0.842),
        Band.create(name="B8A", description="", common_name="Narrow NIR", center_wavelength=0.865),
        Band.create(name="B9", description="", common_name="Water", center_wavelength=0.945),
        Band.create(name="B10", description="", common_name="SWIR - Cirrus", center_wavelength=1.373),
        Band.create(name="B11", description="", common_name="SWIR 1", center_wavelength=1.61),
        Band.create(name="B12", description="", common_name="SWIR 2", center_wavelength=2.190),
    ]
    s2_index = [band.name for band in s2_bands]

    def __init__(self, catalog_path=None, sid=None, title=None, cog=False, with_bbox=True):
        self.catalog_path = catalog_path
        self._catalog = None
        self.sid = sid
        self.title = title
        self.cog = cog
        self.with_bbox = with_bbox

    @property
    def catalog(self):
        """Check if catalog exists and create it otherwise."""
        if self.catalog_path is not None and self._catalog is None:
            if os.path.isfile(self.catalog_path):
                os.remove(self.catalog_path)
            if self.with_bbox:
                self._catalog = pystac.Collection(id="Sen2Like_catalog" if self.sid is None else self.sid,
                                                  title="Sen2Like Catalog" if self.title is None else self.title,
                                                  href=self.catalog_path,
                                                  description="Catalog containing Sen2Like generated products",
                                                  extent=pystac.Extent(pystac.SpatialExtent([180, -56, 180, 83]),
                                                                       pystac.TemporalExtent([None, None])))
            else:
                self._catalog = pystac.Catalog(id="Sen2Like_catalog" if self.sid is None else self.sid,
                                               title="Sen2Like Catalog" if self.title is None else self.title,
                                               href=self.catalog_path,
                                               description="Catalog containing Sen2Like generated products")

        return self._catalog

    def _create_item(self, product, product_id, output_name, ref_image):
        # Get common properties from B04

        # If file is not found, it may have been generated with old version where image format was not correclty managed
        if not os.path.exists(ref_image) and ref_image.endswith('.jp2'):
            ref_image = f"{ref_image[:-4]}.TIF"

        bbox, footprint = get_bbox_and_footprint(ref_image)

        # Create item
        eo_item = pystac.Item(id=product_id,
                              geometry=footprint,
                              bbox=bbox,
                              datetime=product.acqdate,
                              properties={},
                              href=os.path.normpath(output_name))

        EOExtension.add_to(eo_item)
        eo_ext = EOExtension.ext(eo_item)
        eo_ext.apply(bands=self.s2_bands)
        eo_item.properties["Platform"] = product.sensor
        eo_item.properties["Instrument"] = product.mtl.sensor
        eo_item.properties["Sun azimuth"] = f"{float(product.mtl.sun_azimuth_angle):.3f}\u00b0"
        eo_item.properties["Sun elevation"] = f"{float(product.mtl.sun_zenith_angle):.3f}\u00b0"
        eo_item.properties["Processing level"] = os.path.basename(ref_image).split('_')[0]
        eo_item.properties[
            "Cloud cover"] = f"{float(product.mtl.cloud_cover):.2f}%" if product.mtl.cloud_cover is not None else None
        return eo_item

    def write_product(self, product, output_dir, bands, ql_name, granule_compact_name):
        product_id = os.path.basename(output_dir).split('.')[0]
        output_name = f"{os.path.join(output_dir, product_id)}.json"

        item = self._create_item(product, product_id, output_name, bands[0])
        # sort mainly to avoid error during compare with ref file in tests
        for image in sorted(set(bands)):
            band = image.split('_')[-2]
            if not os.path.exists(image) and image.endswith('.jp2'):
                log.warning("Overwrite .jp2 extension from metadata -> image file is a TIF !!!!!")
                image = f"{image[:-4]}.TIF"
            asset = pystac.Asset(href=os.path.normpath(image),
                                 media_type=pystac.MediaType.COG if self.cog else (
                                     pystac.MediaType.GEOTIFF if image.endswith(
                                         ".TIF") else pystac.MediaType.JPEG2000),
                                 extra_fields={
                                     'eo:bands': [self.s2_index.index(band)] if band in self.s2_index else []})
            item.add_asset(band, asset)

            # Get Quicklook
            ql_path = os.path.join(output_dir, 'GRANULE', granule_compact_name, 'QI_DATA', ql_name)
            if os.path.isfile(ql_path):
                ql_asset = pystac.Asset(href=os.path.normpath(ql_path),
                                        media_type=pystac.MediaType.JPEG)
                item.add_asset("thumbnail", ql_asset)
            else:
                log.warning("%s not found: No thumbnail for band %s", ql_path, band)

        item.save_object()
        log.debug("STAC file generated: %s", output_name)

        if self.catalog_path is not None:
            try:
                self.catalog.add_item(item, title=product_id)
            except urllib.error.URLError as error:
                log.error("Cannot write to catalog: %s", error)

    def write_catalog(self):
        if self.catalog is None:
            log.error("Cannot write an empty catalog.")
        else:
            if self.with_bbox and isinstance(self.catalog, pystac.Collection) and len(
                    list(self.catalog.get_all_items())):
                self.catalog.update_extent_from_items()
            self.catalog.save(catalog_type=pystac.CatalogType.ABSOLUTE_PUBLISHED)
            log.debug("STAC catalog generated: %s", self.catalog_path)


class STACReader:

    def __init__(self, stac_file):
        self.stac_file = stac_file

    @classmethod
    def read(cls, stac_file):
        stac_object = pystac.read_file(stac_file)
        return stac_object

    def get__(self):
        pass


class S2LSTACCatalog(pystac.Catalog):

    def __init__(self, sid="Sen2Like_catalog", title="Sen2Like Catalog"):
        super().__init__(
            id=sid,
            title=title,
            description="Catalog containing Sen2Like generated products",
        )

    def write_catalog(self, outdir, outdir_url):
        """
        :param outdir: The directory where catalago is save
        :param outdir_url: The url to accesse at the outdir
        """
        self.normalize_hrefs(outdir_url)
        # Remove collection file (due to dest_href that create dict with same path)
        for col in self.get_collections():
            colfile = os.path.join(outdir, col.id, 'collection.json')
            if os.path.isfile(colfile):
                os.remove(colfile)
            for item in col.get_all_items():
                itempath = os.path.join(outdir, col.id, item.id)
                if os.path.isdir(itempath):
                    shutil.rmtree(itempath)

        self.save(catalog_type=pystac.CatalogType.ABSOLUTE_PUBLISHED, dest_href=outdir)

        # Fix collection save dir, dest_href don't work properly
        for col in self.get_collections():
            colpath = os.path.join(outdir, col.id)
            badpath = os.path.join(colpath, 'collection_badpath')
            shutil.move(os.path.join(colpath, 'collection.json'), badpath)
            contents = glob.glob(os.path.join(badpath, '*'))
            for path in contents:
                shutil.move(path, colpath)
            shutil.rmtree(badpath)


class S2LSTACCatalog_Tile(pystac.Collection):

    bbox = [180, -56, 180, 83]

    def __init__(self, sid, title):
        super().__init__(
            id=sid,
            title=title,
            description="Catalog containing Sen2Like generated products",
            extent=pystac.Extent(pystac.SpatialExtent(self.bbox), pystac.TemporalExtent([None, None]))
        )


class S2LSTACCatalog_Product(pystac.Item):

    s2_bands = [
        Band.create(name="B01", description="", common_name="Coastal aerosol", center_wavelength=0.443),
        Band.create(name="B02", description="", common_name="Blue", center_wavelength=0.49),
        Band.create(name="B03", description="", common_name="Green", center_wavelength=0.56),
        Band.create(name="B04", description="", common_name="Red", center_wavelength=0.665),
        Band.create(name="B05", description="", common_name="Red Edge 1", center_wavelength=0.705),
        Band.create(name="B06", description="", common_name="Red Edge 2", center_wavelength=0.740),
        Band.create(name="B07", description="", common_name="Red Edge 3", center_wavelength=0.783),
        Band.create(name="B08", description="", common_name="NIR", center_wavelength=0.842),
        Band.create(name="B8A", description="", common_name="Narrow NIR", center_wavelength=0.865),
        Band.create(name="B9", description="", common_name="Water", center_wavelength=0.945),
        Band.create(name="B10", description="", common_name="SWIR - Cirrus", center_wavelength=1.373),
        Band.create(name="B11", description="", common_name="SWIR 1", center_wavelength=1.61),
        Band.create(name="B12", description="", common_name="SWIR 2", center_wavelength=2.190),
    ]
    s2_index = [band.name for band in s2_bands]

    def __init__(self, product, product_url, ref_band, cog=False):
        product_id = product.name.split('.')[0]
        ref_image = self._fix_image_particule(product.mtl.bands[ref_band])
        bbox, footprint = get_bbox_and_footprint(ref_image)
        super().__init__(
            id=product_id,
            geometry=footprint,
            properties={},
            bbox=bbox,
            datetime=product.acqdate
        )

        EOExtension.add_to(self)
        eo_ext = EOExtension.ext(self)
        eo_ext.apply(bands=self.s2_bands)
        self.properties["Platform"] = product.sensor
        self.properties["Instrument"] = product.mtl.sensor
        self.properties["Sun azimuth"] = f"{float(product.mtl.sun_azimuth_angle):.3f}\u00b0"
        self.properties["Sun elevation"] = f"{float(product.mtl.sun_zenith_angle):.3f}\u00b0"
        self.properties["Processing level"] = os.path.basename(ref_image).split('_')[0]
        self.properties[
            "Cloud cover"] = f"{float(product.mtl.cloud_cover):.2f}%" if product.mtl.cloud_cover is not None else None

        self.cog = cog
        self.product = product
        self.product_url = product_url

    @staticmethod
    def _fix_image_particule(image):
        if not os.path.exists(image) and image.endswith('.jp2'):
            log.warning("Overwrite .jp2 extension from metadata -> image file is a TIF !!!!!")
            return f"{image[:-4]}.TIF"
        return image

    def add_product_bands_asset(self):
        for band, image in self.product.mtl.bands.items():
            image = self._fix_image_particule(image)
            rel_path = os.path.relpath(image, self.product.path)
            url = self.product_url + '/' + rel_path

            asset = pystac.Asset(href=url,
                                 media_type=pystac.MediaType.COG if self.cog else (
                                     pystac.MediaType.GEOTIFF if image.endswith(
                                         ".TIF") else pystac.MediaType.JPEG2000),
                                 extra_fields={
                                     'eo:bands': [self.s2_index.index(band)] if band in self.s2_index else []})
            self.add_asset(band, asset)

    def add_quicklook_asset(self, granule_compact_name, ql_name):
        # granule_compact_name and ql_name are not necessary in product object (i.e. landsat)
        rel_path = os.path.join('GRANULE', granule_compact_name, 'QI_DATA', ql_name)
        url = self.product_url + '/' + rel_path
        ql_asset = pystac.Asset(href=url,
                                media_type=pystac.MediaType.JPEG)
        self.add_asset("thumbnail", ql_asset)
