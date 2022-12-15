#!/usr/bin/env python
#
# (C) Copyright 2019 Telespazio France


import numpy as np
from osgeo import gdal
from skimage.morphology import binary_closing, binary_opening, binary_dilation, disk, square

# inputs
# scl_image = sys.argv[1]
# output_mask = sys.argv[2]
scl_image = r"E:\data\L2A_T31TFJ_20170113T104401_SCL_60m.tif"
output_mask = r"E:\data\S2L_31TFJ_20170113_S2_SCL.disk.TIF"

# read SCL
src_ds = gdal.Open(scl_image)
scl_band = src_ds.GetRasterBand(1)
scl_array = scl_band.ReadAsArray()

# Consider as valid pixels :
#                VEGETATION et NOT_VEGETATED (valeurs 4 et 5)
#                UNCLASSIFIED (7)
#                excluded SNOW (11)
valid_px_mask = np.zeros(scl_array.shape, np.uint8)
valid_px_mask[scl_array == 0] = 0  # NO_DATA
valid_px_mask[scl_array == 1] = 0  # SATURATED OR DEFECTIVE
valid_px_mask[scl_array == 2] = 0  # DARK AREA -> should evolve to topographic shadows
valid_px_mask[scl_array == 3] = 0  # CLOUD SHADOWS
valid_px_mask[scl_array == 4] = 1  # VEGETATION
valid_px_mask[scl_array == 5] = 1  # NOT VEGETATED
valid_px_mask[scl_array == 6] = 0  # WATER
valid_px_mask[scl_array == 7] = 1  # UNCLASSIFIED can be border of clouds but also interesting pixels.
valid_px_mask[scl_array == 8] = 0  # MEDIUM PROBA CLOUDS
valid_px_mask[scl_array == 9] = 0  # HIGH PROBA CLOUDS
valid_px_mask[scl_array == 10] = 0  # THIN CIRRUS
valid_px_mask[scl_array == 11] = 0  # SNOW ICE


# Soft dilatation of Cloud mask (120 m dilatation) 60m processing
def filter_isolated_cells(image, struct):
    """ Return array with completely isolated single cells removed
    :param image: Array with completely isolated single cells
    :param struct: Structure array for generating unique regions
    :return: Array with minimum region size > 1
    """
    from scipy import ndimage
    filtered_image = np.copy(image)
    id_regions, num_ids = ndimage.label(filtered_image, structure=struct)
    id_sizes = np.array(ndimage.sum(image, id_regions, list(range(num_ids + 1))))
    area_mask = (id_sizes <= 3)
    filtered_image[area_mask[id_regions]] = 0

    return filtered_image


# dilate mask
"""
from skimage.morphology import disk, square, diamond, dilation, closing, opening
valid_px_mask = np.invert(valid_px_mask)
valid_px_mask = closing(valid_px_mask, disk(3))
#valid_px_mask = dilation(valid_px_mask, square(5))
valid_px_mask = np.invert(valid_px_mask)
"""

# invert mask
valid_px_mask = np.logical_not(valid_px_mask)

# filter
valid_px_mask = filter_isolated_cells(valid_px_mask, struct=np.ones((3, 3)))

# Dilatation square operator (5x5)
"""
from scipy.ndimage.morphology import binary_dilation
valid_px_mask = binary_dilation(valid_px_mask, np.ones((5, 5)))
"""

# Closing

# valid_px_mask = closing(valid_px_mask, disk(5))
# valid_px_mask = erosion(valid_px_mask, square(3))
# valid_px_mask = binary_dilation(valid_px_mask, disk(5))
valid_px_mask = binary_closing(valid_px_mask, disk(5))
valid_px_mask = binary_opening(valid_px_mask, disk(2))
valid_px_mask = binary_dilation(valid_px_mask, square(3))

# invert mask back
valid_px_mask = np.logical_not(valid_px_mask)

# create temporary driver
# driver = gdal.GetDriverByName('MEM')
driver = gdal.GetDriverByName('GTiff')
tmp_ds = driver.CreateCopy(output_mask.replace('.TIF', '_60m.TIF'), src_ds, 0)
tmp_ds.GetRasterBand(1).WriteArray(valid_px_mask, 0, 0)

# resample to 30m
result = gdal.Translate(output_mask, tmp_ds, creationOptions=['COMPRESS=LZW'], xRes=30, yRes=30, resampleAlg='mode')
print('Written:', output_mask)
