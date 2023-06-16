# -*- coding: utf-8 -*-

# CODE FROM SEN2LIKE ADAPTED FOR PRISMA4SEN2LIKE NEEDS
# NOTE THAT SOME CODE BLOCK ARE USELESS, CODE HAVE NOT BEEN CLEANED

import logging
import os

import numpy as np
from osgeo import gdal, osr

log = logging.getLogger(__name__)


class S2L_ImageFile:
    FILE_EXTENSIONS = {
        "GTIFF": "TIF",
        "COG": "TIF",
        "JPEG2000": "jp2",
    }

    def __init__(self, path, mode="r"):
        self.setFilePath(path)

        # geo information
        if mode == "r":
            self.readHeader()
        else:
            self.xSize = None
            self.ySize = None
            self.xRes = None
            self.yRes = None
            self.xMin = None
            self.yMax = None
            self.xMax = None
            self.yMin = None
            self.projection = None

        # really read only if array attribute is accessed (see array property)
        self._array = None

    def setFilePath(self, path):
        # file name, path, dirname
        self.filepath = path
        self.filename = os.path.basename(path)
        self.rootname, self.ext = os.path.splitext(self.filename)
        self.dirpath = os.path.dirname(path)
        self.dirname = os.path.basename(self.dirpath)

    @property
    def array(self):
        """ "Access to image array (numpy array)"""

        # read file is not already done
        if self._array is None:
            self.read()
        return self._array

    def readHeader(self):
        # geo information
        dst = gdal.Open(self.filepath)
        geo = dst.GetGeoTransform()
        self.xSize = dst.RasterXSize
        self.ySize = dst.RasterYSize
        self.xRes = geo[1]
        self.yRes = geo[5]
        self.xMin = geo[0]
        self.yMax = geo[3]
        self.xMax = self.xMin + self.xSize * self.xRes
        self.yMin = self.yMax + self.ySize * self.yRes
        self.projection = dst.GetProjection()
        dst = None

    def copyHeaderTo(self, new):
        # geo information
        new.xSize = self.xSize
        new.ySize = self.ySize
        new.xRes = self.xRes
        new.yRes = self.yRes
        new.xMin = self.xMin
        new.yMax = self.yMax
        new.xMax = self.xMax
        new.yMin = self.yMin
        new.projection = self.projection

    def getCorners(self, outWKT=None, outEPSG=None, outPROJ4=None):
        """
        Return the coordinates of the image corners, possibly reprojected.

        This is the same information as in the xMin, xMax, yMin, yMax fields,
        but with the option to reproject them into a given output projection.
        Because the output coordinate system will not in general align with the
        image coordinate system, there are separate values for all four corners.
        These are returned as::

            (ul_x, ul_y, ur_x, ur_y, lr_x, lr_y, ll_x, ll_y)

        The output projection can be given as either a WKT string, an
        EPSG number, or a PROJ4 string. If none of those is given, then
        bounds are not reprojected, but will be in the same coordinate
        system as the image corners.

        Source: rios library

        """
        if outWKT is not None:
            outSR = osr.SpatialReference(wkt=outWKT)
        elif outEPSG is not None:
            outSR = osr.SpatialReference()
            outSR.ImportFromEPSG(int(outEPSG))
        elif outPROJ4 is not None:
            outSR = osr.SpatialReference()
            outSR.ImportFromProj4(outPROJ4)
        else:
            outSR = None

        if outSR is not None:
            inSR = osr.SpatialReference(wkt=self.projection)
            if hasattr(outSR, "SetAxisMappingStrategy"):
                outSR.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)
            t = osr.CoordinateTransformation(inSR, outSR)
            (ul_x, ul_y, z) = t.TransformPoint(self.xMin, self.yMax)
            (ll_x, ll_y, z) = t.TransformPoint(self.xMin, self.yMin)
            (ur_x, ur_y, z) = t.TransformPoint(self.xMax, self.yMax)
            (lr_x, lr_y, z) = t.TransformPoint(self.xMax, self.yMin)
        else:
            (ul_x, ul_y) = (self.xMin, self.yMax)
            (ll_x, ll_y) = (self.xMin, self.yMin)
            (ur_x, ur_y) = (self.xMax, self.yMax)
            (lr_x, lr_y) = (self.xMax, self.yMin)

        return ul_x, ul_y, ur_x, ur_y, lr_x, lr_y, ll_x, ll_y

    def read(self):
        dst = gdal.Open(self.filepath)
        band = dst.GetRasterBand(1)
        self._array = band.ReadAsArray()
        dst = None

    def crop(self, box):
        """
        read only a roi from file
        :param box: tuple of (xoff, yoff, xsize, ysize)
        :return: array
        """

        # read box
        xoff, yoff, win_xsize, win_ysize = box

        # read
        dst = gdal.Open(self.filepath)
        band = dst.GetRasterBand(1)
        data = band.ReadAsArray(xoff, yoff, win_xsize, win_ysize)
        dst = None
        return data

    def duplicate(self, filepath, array=None, res=None, origin=None, output_EPSG=None) -> "S2L_ImageFile":
        # case array is not provided (default)
        if array is None:
            array = self._array

        # init new instance, copy header, # set array and return new instance
        new_image = S2L_ImageFile(filepath, mode="w")
        self.copyHeaderTo(new_image)

        if array is not None:
            new_image.xSize = array.shape[1]
            new_image.ySize = array.shape[0]

        if res is not None:
            new_image.xRes = res
            # pylint: disable=invalid-unary-operand-type
            new_image.yRes = -res

        if origin is not None:
            # origin is a tuple with xMin and yMax (same def as in gdal)
            new_image.xMin = origin[0]
            new_image.yMax = origin[1]
            new_image.xMax = new_image.xMin + new_image.xSize * new_image.xRes
            new_image.yMin = new_image.yMax + new_image.ySize * new_image.yRes

        if output_EPSG is not None:
            new_srs = osr.SpatialReference()
            new_srs.ImportFromEPSG(int(output_EPSG))
            new_image.projection = new_srs.ExportToWkt()

        #  data
        new_image._array = array

        # check dimensions
        if array.shape[0] != new_image.ySize or array.shape[1] != new_image.xSize:
            log.error(
                "ERROR: Input array dimensions do not fit xSize and ySize defined in the file header to be duplicated"
            )
            return None

        return new_image

    def write(
        self,
        creation_options=None,
        DCmode=False,
        filepath=None,
        nodata_value=None,
        output_format: str = "GTIFF",
        band: str = None,
        no_data_mask=None,
    ):
        """
        write to file
        :param creation_options: gdal create options
        :param DCmode: if true, the type is kept. Otherwise float are converted to int16 using
        offset and gain from config
        :param filepath:
        :param output_format: writed file format ('GTIFF' for geotiff, 'COG' for COG and 'JPEG2000' for jpeg2000)
        :param band : provide information about the band, to set the overviews downsampling algorithm.
                      band can be 'MASK', 'QA', or None for all others
        :param no_data_mask: (array with same shape than image) If image type is float,  and no DCmode
                            set to nodata_value all mask value, and increase by 1 all other value equal with
                            nodata_value.
        """
        if creation_options is None:
            creation_options = []

        # if filepath is override
        if filepath is None:
            filepath = self.filepath

        # Ensure file extension
        if not filepath.upper().endswith(self.FILE_EXTENSIONS[output_format]):
            filepath = os.path.splitext(filepath)[0] + "." + self.FILE_EXTENSIONS[output_format]

        # check if directory to create
        if not os.path.exists(self.dirpath):
            os.makedirs(self.dirpath)

        # write with gdal
        e_type = gdal.GetDataTypeByName(self.array.dtype.name)
        if self.array.dtype.name.endswith("int8"):
            # work around to GDT_Unknown
            e_type = 1
        elif "float" in self.array.dtype.name and not DCmode:
            # float to UInt16
            e_type = gdal.GDT_UInt16

        # Update image attributes
        self.setFilePath(filepath)

        # Create folders hierarchy if needed:
        if not os.path.exists(self.dirpath):
            os.makedirs(self.dirpath)

        if output_format == "GTIFF":
            driver = gdal.GetDriverByName("GTiff")
            dst_ds = driver.Create(
                self.filepath, xsize=self.xSize, ysize=self.ySize, bands=1, eType=e_type, options=creation_options
            )
        else:
            driver = gdal.GetDriverByName("MEM")
            dst_ds = driver.Create("", xsize=self.xSize, ysize=self.ySize, bands=1, eType=e_type)

        dst_ds.SetProjection(self.projection)
        geo_transform = (self.xMin, self.xRes, 0, self.yMax, 0, self.yRes)
        log.debug(geo_transform)
        dst_ds.SetGeoTransform(geo_transform)

        if "float" in self.array.dtype.name and not DCmode:
            # float to UInt16 with scaling factor of 10000
            gain = 10000.0
            offset = 1000.0

            array_out = (self.array.clip(min=0) * gain + offset).astype(np.uint16)

            # set no data to zero
            array_out[np.isnan(self.array)] = nodata_value

            dst_ds.GetRasterBand(1).WriteArray(array_out)
            # set GTiff metadata
            dst_ds.GetRasterBand(1).SetScale(1 / gain)
            dst_ds.GetRasterBand(1).SetOffset(-offset / gain)
        else:
            dst_ds.GetRasterBand(1).WriteArray(self.array)

        if nodata_value is not None:
            dst_ds.GetRasterBand(1).SetNoDataValue(nodata_value)

        if output_format == "JPEG2000":
            driver_JPG = gdal.GetDriverByName("JP2OpenJPEG")

            # Overloading creation options
            creation_options = dict(map(lambda o: o.split("="), creation_options))
            if S2L_config.config.getboolean("lossless_jpeg2000"):
                creation_options["QUALITY"] = 100
                creation_options["REVERSIBLE"] = "YES"
                creation_options["YCBCR420"] = "NO"

            if self.xRes == 60:
                creation_options.update(
                    {
                        "CODEBLOCK_WIDTH": 4,
                        "CODEBLOCK_HEIGHT": 4,
                        "BLOCKXSIZE": 192,
                        "BLOCKYSIZE": 192,
                        "PROGRESSION": "LRCP",
                        "PRECINCTS": "{64,64},{64,64},{64,64},{64,64},{64,64},{64,64}",
                    }
                )
            elif self.xRes == 20:
                creation_options.update(
                    {
                        "CODEBLOCK_WIDTH": 8,
                        "CODEBLOCK_HEIGHT": 8,
                        "BLOCKXSIZE": 640,
                        "BLOCKYSIZE": 640,
                        "PROGRESSION": "LRCP",
                        "PRECINCTS": "{128,128},{128,128},{128,128},{128,128},{128,128},{128,128}",
                    }
                )
            elif self.xRes == 10:
                creation_options.update(
                    {
                        "CODEBLOCK_WIDTH": 64,
                        "CODEBLOCK_HEIGHT": 64,
                        "BLOCKXSIZE": 1024,
                        "BLOCKYSIZE": 1024,
                        "PROGRESSION": "LRCP",
                        "PRECINCTS": "{256,256},{256,256},{256,256},{256,256},{256,256},{256,256}",
                    }
                )
            creation_options = list(map(lambda ops: ops[0] + "=" + str(ops[1]), creation_options.items()))

            # pylint: disable=unused-variable
            data_set2 = driver_JPG.CreateCopy(self.filepath, dst_ds, options=creation_options)
            # this is the way to close gdal dataset
            data_set2 = None

        if output_format == "COG":
            resampling_algo = (
                S2L_config.config.get("resampling_algo_MASK")
                if band in ["QA", "MASK"]
                else S2L_config.config.get("resampling_algo")
            )
            downsampling_levels = S2L_config.config.get(
                "downsampling_levels_{}".format(int(self.xRes)), S2L_config.config.get("downsampling_levels_10")
            )  # If the res isn't [10, 15, 20, 30, 60], consider it as 30
            downsampling_levels = [int(x) for x in downsampling_levels.split(" ")]

            # Overloading creation options
            creation_options = dict(map(lambda o: o.split("="), creation_options))
            creation_options.update(
                {
                    "TILED": "YES",
                    "COMPRESS": S2L_config.config.get("compression"),
                    "INTERLEAVE": S2L_config.config.get("interleave"),
                    "BLOCKXSIZE": str(S2L_config.config.get("internal_tiling")),
                    "BLOCKYSIZE": str(S2L_config.config.get("internal_tiling")),
                    "PREDICTOR": str(S2L_config.config.get("predictor")),
                }
            )
            creation_options = list(map(lambda ops: ops[0] + "=" + str(ops[1]), creation_options.items()))
            # FIXME : in this gdal version, driver GTiff does not support creation option GDAL_TIFF_OVR_BLOCKSIZE
            # FIXME : to set the internal overview blocksize ; however it is set at 128 as default, as requested here
            # Source : https://gdal.org/drivers/raster/gtiff.html#raster-gtiff
            # add in options : "GDAL_TIFF_OVR_BLOCKSIZE=" + str(config.get('internal_overviews'))

            dst_ds.BuildOverviews(resampling_algo, downsampling_levels)
            driver_Gtiff = gdal.GetDriverByName("GTiff")
            try:
                data_set2 = driver_Gtiff.CreateCopy(
                    self.filepath, dst_ds, options=creation_options + ["COPY_SRC_OVERVIEWS=YES"]
                )
                data_set2 = None  # noqa: F841
            except RuntimeError as err:
                log.error(err)

            else:
                log.info("Written: %s", self.filepath)

        dst_ds.FlushCache()
        dst_ds = None
