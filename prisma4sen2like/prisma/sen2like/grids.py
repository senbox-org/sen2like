#! /usr/bin/env python
# -*- coding: utf-8 -*-
# V. Debaecker (TPZ-F) 2018

import os
import sqlite3
from dataclasses import dataclass
from os.path import dirname

import mgrs
import pandas as pd
from osgeo import ogr, osr
from shapely.geometry.base import BaseGeometry

current_dir = dirname(__file__)
DB_file = os.path.join(current_dir, "s2tiles.db")


@dataclass
class MGRSGeoInfo:
    """MGRS tile geo info"""

    tile_id: str
    "Tile id"
    epsg: str
    """tile epsg"""
    geometry: BaseGeometry
    """tile geometry as UTM coords"""


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
            f'SELECT TILE_ID, EPSG, UTM_WKT, MGRS_REF, LL_WKT FROM s2tiles WHERE TILE_ID="{tilecode}"',  # nosec B608
            self.conn,
        )

    def close(self):
        self.conn.close()

    def getROIfromMGRS(self, tilecode):
        # read db and get "sites" table
        if tilecode.startswith("T"):
            tilecode = tilecode[1:]

        roi = self._get_roi(tilecode)

        # return as dict
        return roi.to_dict(orient="list")

    def get_mgrs_center(self, tilecode, utm=False):
        if tilecode.startswith("T"):
            tilecode = tilecode[1:]

        centercode = tilecode + "5490045100"
        m = mgrs.MGRS()

        if utm:
            return m.MGRSToUTM(centercode)

        return m.toLatLon(centercode)

    # Don't know why but with this method the SRS code is not added in the geojson
    # if the GDAL_DATA variable is set in the environment. However we need
    # this GDAL_DATA variable for other methods. So we do not use this method.
    def wktToJson2(self, wkt, epsg_code, filename):
        # polygon from wkt
        multipolygon = ogr.CreateGeometryFromWkt(wkt)

        # Create srs
        srs = osr.SpatialReference()
        srs.ImportFromEPSG(int(epsg_code))

        # Create the output Driver
        outDriver = ogr.GetDriverByName("GeoJSON")

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
    def wktToJson(self, wkt, epsg_code, filename):
        # polygon from wkt, to geojson string
        multipolygon = ogr.CreateGeometryFromWkt(wkt)
        geojson = multipolygon.ExportToJson()

        param = "{\n"
        param += '"type": "FeatureCollection",\n'
        param += '"crs": { "type": "name", "properties": { "name": "urn:ogc:def:crs:EPSG::' + epsg_code + '" } },\n'
        param += '"features": [\n'
        param += '{ "type": "Feature", "properties": { "prop0": null }, "geometry":'

        with open(filename, "w", encoding="UTF-8") as f:
            f.write(param)
            f.write(geojson + "}]}")
