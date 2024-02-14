#! /usr/bin/env python
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


import os
import sqlite3
from os.path import abspath, dirname

import mgrs
import pandas as pd
from osgeo import ogr, osr
from shapely.wkt import loads

sen2like_dir = abspath(dirname(dirname(__file__)))
DB_file = os.path.join(sen2like_dir, 'core/product_archive/data/s2tiles.db')


class GridsConverter:
    """
    Class for accessing the MGRS Tiles and Sites database
    and make requests
    """

    def __init__(self):
        self.conn = sqlite3.connect(DB_file)

    def _get_roi(self, tilecode):
        # search tilecode in "s2tiles" and return row as a pandas dataframe
        return pd.read_sql_query(
            'SELECT TILE_ID, EPSG, UTM_WKT, MGRS_REF, LL_WKT FROM s2tiles WHERE TILE_ID="{}"'.format(tilecode),
            self.conn)

    def close(self):
        self.conn.close()

    def getROIfromMGRS(self, tilecode):

        # read db and get "sites" table
        if tilecode.startswith('T'):
            tilecode = tilecode[1:]
        roi = self._get_roi(tilecode)

        # return as dict
        return roi.to_dict(orient='list')

    def get_mgrs_center(self, tilecode, utm=False):
        if tilecode.startswith('T'):
            tilecode = tilecode[1:]
        centercode = tilecode + '5490045100'
        m = mgrs.MGRS()
        if utm:
            return m.MGRSToUTM(centercode)
        return m.toLatLon(centercode)

    # Don't know why but with this method the SRS code is not added in the geojson
    # if the GDAL_DATA variable is set in the environment. However we need
    # this GDAL_DATA variable for other methods. So we do not use this method.
    def WktToJson2(self, wkt, epsg_code, filename):

        # polygon from wkt
        multipolygon = ogr.CreateGeometryFromWkt(wkt)

        # Create srs
        srs = osr.SpatialReference()
        srs.ImportFromEPSG(int(epsg_code))

        # Create the output Driver
        outDriver = ogr.GetDriverByName('GeoJSON')

        # Create the output GeoJSON
        if not os.path.exists(os.path.dirname(filename)):
            os.makedirs(os.path.dirname(filename))
        outDataSource = outDriver.CreateDataSource(filename)
        outLayer = outDataSource.CreateLayer(filename, srs=srs, geom_type=ogr.wkbPolygon)

        # Get the output Layer's Feature Definition,
        # create a new feature and set new geometry
        featureDefn = outLayer.GetLayerDefn()
        outFeature = ogr.Feature(featureDefn)
        outFeature.SetGeometry(multipolygon)

        # Add new feature to output Layer
        outLayer.CreateFeature(outFeature)

        # dereference the feature, save and close DataSources
        outFeature = None
        outDataSource = None

    # Manual export...
    def WktToJson(self, wkt, epsg_code, filename):

        # polygon from wkt, to geojson string
        multipolygon = ogr.CreateGeometryFromWkt(wkt)
        geojson = multipolygon.ExportToJson()

        param = "{\n"
        param += "\"type\": \"FeatureCollection\",\n"
        param += "\"crs\": { \"type\": \"name\", \"properties\": { \"name\": \"urn:ogc:def:crs:EPSG::" + \
                 epsg_code + "\" } },\n"
        param += "\"features\": [\n"
        param += "{ \"type\": \"Feature\", \"properties\": { \"prop0\": null }, \"geometry\":"

        with open(filename, 'w') as f:
            f.write(param)
            f.write(geojson + '}]}')

    def get_corners(self, mgrs_tile, out_wkt=None, out_epsg=None, out_proj4=None):
        """
        Return the coordinates of the mgrs corners, possibly reprojected.

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
        tile = self.getROIfromMGRS(mgrs_tile)
        utm_geom = loads(tile["UTM_WKT"][0])
        _coords = list(utm_geom.envelope.exterior.coords)
        _x_coords = [c[0] for c in _coords]
        _y_coords = [c[1] for c in _coords]
        x_min = min(_x_coords)
        x_max = max(_x_coords)
        y_min = min(_y_coords)
        y_max = max(_y_coords)

        if out_wkt is not None:
            out_srs = osr.SpatialReference(wkt=out_wkt)
        elif out_epsg is not None:
            out_srs = osr.SpatialReference()
            out_srs.ImportFromEPSG(int(out_epsg))
        elif out_proj4 is not None:
            out_srs = osr.SpatialReference()
            out_srs.ImportFromProj4(out_proj4)
        else:
            out_srs = None

        if out_srs is not None:
            in_srs = osr.SpatialReference()
            in_srs.ImportFromEPSG(int(tile['EPSG'][0]))
            if hasattr(out_srs, 'SetAxisMappingStrategy'):
                out_srs.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)
            t = osr.CoordinateTransformation(in_srs, out_srs)
            (ul_x, ul_y, z) = t.TransformPoint(x_min, y_max)
            (ll_x, ll_y, z) = t.TransformPoint(x_min, y_min)
            (ur_x, ur_y, z) = t.TransformPoint(x_max, y_max)
            (lr_x, lr_y, z) = t.TransformPoint(x_max, y_min)
        else:
            (ul_x, ul_y) = (x_min, y_max)
            (ll_x, ll_y) = (x_min, y_min)
            (ur_x, ur_y) = (x_max, y_max)
            (lr_x, lr_y) = (x_max, y_min)

        return ul_x, ul_y, ur_x, ur_y, lr_x, lr_y, ll_x, ll_y
