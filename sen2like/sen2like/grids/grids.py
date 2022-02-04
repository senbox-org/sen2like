#! /usr/bin/env python
# -*- coding: utf-8 -*-
# V. Debaecker (TPZ-F) 2018

import os
from os.path import dirname, abspath
import sqlite3

import pandas as pd
import mgrs
from osgeo import ogr, osr

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
