import logging
import os
import shutil

import numpy as np
from osgeo import gdal, osr

from core.S2L_config import config

log = logging.getLogger("Sen2Like")


class S2L_ImageFile:

    def __init__(self, path, mode='r'):
        self.setFilePath(path)

        # geo information
        if mode == 'r':
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
        """"Access to image array (numpy array)"""

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
            if hasattr(outSR, 'SetAxisMappingStrategy'):
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

    def duplicate(self, filepath, array=None, res=None, origin=None, output_EPSG=None):

        # case array is not provided (default)
        if array is None:
            array = self._array

        # init new instance, copy header, # set array and return new instance
        newInstance = S2L_ImageFile(filepath, mode='w')
        self.copyHeaderTo(newInstance)

        if array is not None:
            newInstance.xSize = array.shape[1]
            newInstance.ySize = array.shape[0]

        if res is not None:
            newInstance.xRes = res
            newInstance.yRes = -res

        if origin is not None:
            # origin is a tuple with xMin and yMax (same def as in gdal)
            newInstance.xMin = origin[0]
            newInstance.yMax = origin[1]
            newInstance.xMax = newInstance.xMin + newInstance.xSize * newInstance.xRes
            newInstance.yMin = newInstance.yMax + newInstance.ySize * newInstance.yRes

        if output_EPSG is not None:
            new_SRS = osr.SpatialReference()
            new_SRS.ImportFromEPSG(int(output_EPSG))
            newInstance.projection = new_SRS.ExportToWkt()

        #  data
        newInstance._array = array

        # check dimensions
        if array.shape[0] != newInstance.ySize or array.shape[1] != newInstance.xSize:
            log.error(
                'ERROR: Input array dimensions do not fit xSize and ySize defined in the file header to be duplicated')
            return None

        return newInstance

    def write(self, creation_options=None, DCmode=False, filepath=None, nodata_value=0, COG:bool=False, band:str=None):
        """
        write to file
        :param creation_options: gdal create options
        :param DCmode: if true, the type is kept. Otherwise float are converted to int16 using
        offset and gain from config
        :param filepath:
        :param COG : whether to create COG output format or not
        :param band : provide information about the band, to set the overviews downsampling algorithm.
                      band can be 'MASK', 'QA', or None for all others
        """
        if creation_options is None:
            creation_options = []

        # if filepath is override
        if filepath is None:
            filepath = self.filepath

        # Ensure that file extension is tiff
        if not filepath.endswith('.tif'):
            filepath = os.path.splitext(filepath)[0] + ".TIF"

        # check if directory to create
        if not os.path.exists(self.dirpath):
            os.makedirs(self.dirpath)

        # write with gdal
        etype = gdal.GetDataTypeByName(self.array.dtype.name)
        if self.array.dtype.name.endswith('int8'):
            # work around to GDT_Unknown
            etype = 1
        elif 'float' in self.array.dtype.name and not DCmode:
            # float to UInt16
            etype = gdal.GDT_UInt16

        # Update image attributes
        self.setFilePath(filepath)

        # Create folders hierarchy if needed:
        if not os.path.exists(self.dirpath):
            os.makedirs(self.dirpath)

        if not COG:
            driver = gdal.GetDriverByName('GTiff')
            dst_ds = driver.Create(self.filepath, xsize=self.xSize,
                                   ysize=self.ySize, bands=1, eType=etype, options=creation_options)
        else:
            driver = gdal.GetDriverByName('MEM')
            dst_ds = driver.Create('', xsize=self.xSize,
                                   ysize=self.ySize, bands=1, eType=etype)

        dst_ds.SetProjection(self.projection)
        geotranform = (self.xMin, self.xRes, 0, self.yMax, 0, self.yRes)
        log.debug(geotranform)
        dst_ds.SetGeoTransform(geotranform)
        if 'float' in self.array.dtype.name and not DCmode:
            # float to UInt16 with scaling factor of 10000
            offset = float(config.get('offset'))
            gain = float(config.get('gain'))
            dst_ds.GetRasterBand(1).WriteArray(((offset + self.array).clip(min=0) * gain).astype(np.uint16))
            # set GTiff metadata
            dst_ds.GetRasterBand(1).SetScale(1 / gain)
            dst_ds.GetRasterBand(1).SetOffset(offset)
        else:
            dst_ds.GetRasterBand(1).WriteArray(self.array)
        if nodata_value:
            dst_ds.GetRasterBand(1).SetNoDataValue(nodata_value)

        if COG:
            resampling_algo = config.get('resampling_algo_MASK') if band in ['QA', 'MASK'] else config.get('resampling_algo')
            downsampling_levels = config.get('downsampling_levels_{}'.format(int(self.xRes)), config.get('downsampling_levels_10'))  # If the res isn't [10, 15, 20, 30, 60], consider it as 30
            downsampling_levels = [int(x) for x in downsampling_levels.split(" ")]

            # Overloading creation options
            creation_options = [opt for opt in creation_options if opt.split("=")[0] not in
                                ['TILED', 'COMPRESS', 'INTERLEAVE', 'BLOCKYSIZE', 'BLOCKXSIZE', 'PREDICTOR']] + \
                               \
                               ['TILED=YES',
                                "COMPRESS=" + config.get('compression'),
                                "INTERLEAVE=" + config.get('interleave'),
                                "BLOCKXSIZE=" + str(config.get('internal_tiling')),
                                "BLOCKYSIZE=" + str(config.get('internal_tiling')),
                                "PREDICTOR=" + str(config.get('predictor'))]
            # FIXME :  in this gdal version, driver GTiff does not support creation option GDAL_TIFF_OVR_BLOCKSIZE to set the
            # FIXME :  internal overview blocksize ; however it is set at 128 as default, as requested here
            # Source : https://gdal.org/drivers/raster/gtiff.html#raster-gtiff
            # add in options : "GDAL_TIFF_OVR_BLOCKSIZE=" + str(config.get('internal_overviews'))

            dst_ds.BuildOverviews(resampling_algo, downsampling_levels)
            driver_Gtiff = gdal.GetDriverByName('GTiff')
            data_set2 = driver_Gtiff.CreateCopy(self.filepath, dst_ds, options=creation_options + ['COPY_SRC_OVERVIEWS=YES'])
            data_set2 = None

        dst_ds.FlushCache()

        dst_ds = None
        log.info('Written: {}'.format(self.filepath))

    def rename(self, newpath):
        """
        Rename file is exists, otherwise write image to newpath
        If renaming to another directory that not exists, create it.
        TODO: Copy metadata also?
        :param newpath: new path
        """
        # check if new directory to create
        newdir = os.path.dirname(newpath)
        if not os.path.exists(newdir):
            os.makedirs(newdir)

        # rename file (move) and reinit class attributes
        log.debug('Moving {}\n\t to {}'.format(self.filepath, newpath))
        shutil.move(self.filepath, newpath)
        self.__init__(newpath)
