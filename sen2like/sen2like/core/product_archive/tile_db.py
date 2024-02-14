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
Facility module to request MGRS and WRS tile db
"""
import logging
import os
import sqlite3
from collections import namedtuple

logger = logging.getLogger("Sen2Like")

S2_TILE_DB = 's2tiles.db'
L8_TILE_DB = 'l8tiles.db'

SELECT_NOT_ON_180TH_MERIDIAN = (
    "SELECT *, "
    "st_x(st_pointn(ST_ExteriorRing({geo_col}), 1)) as p1, "
    "st_x(st_pointn(ST_ExteriorRing({geo_col}), 2)) as p2, "
    "st_x(st_pointn(ST_ExteriorRing({geo_col}), 3)) as p3, "
    "st_x(st_pointn(ST_ExteriorRing({geo_col}), 4)) as p4, "
    "st_x(st_pointn(ST_ExteriorRing({geo_col}), 5)) as p5 "
    "FROM {table} "
    "WHERE p1 between -100 and 100 "
    "OR p1 <= 100 and p2 < 0 and p3 < 0 and p4 < 0 and p5 < 0 "
    "OR p1 >= 100 and p2 > 0 and p3 > 0 and p4 > 0 and p5 > 0 "
)

# named tuple fo "tile to tile" functions
T2TRequest = namedtuple('T2TRequest', ['coverage', 'sql_request'])


def _database_path(database_name):
    return os.path.join(os.path.dirname(__file__), "data", database_name)


def is_spatialite_supported():
    """Check if spatialite is supported by the execution environment

    Returns:
        True if it is, otherwise False
    """
    if os.environ.get("SPATIALITE_DIR") is None:
        logger.warning("SPATIALITE_DIR environment variable not set.")
    else:
        os.environ["PATH"] = ";".join([os.environ["SPATIALITE_DIR"], os.environ["PATH"]])
    with sqlite3.connect(":memory:") as conn:
        conn.enable_load_extension(True)
        try:
            conn.load_extension("mod_spatialite")
        except sqlite3.OperationalError:
            return False
    return True


def _select_on_attache_db(databases, request, parameters):
    """ Attache all database on one memory database and execute request on them
    :param databases: dict of {'data base name use in request': 'path to database'}
    :param request: the sql_request
    :param parameters: sqlite3 request parameters
    """

    logger.debug("_select_on_attache_db Request : %s", request )
    logger.debug("_select_on_attache_db Params  : %s", parameters )

    with sqlite3.connect(":memory:") as conn:
        conn.enable_load_extension(True)
        conn.load_extension("mod_spatialite")
        cur = conn.cursor()
        for name, filepath in databases.items():
            attache = f'ATTACH DATABASE "{filepath}" AS "{name}"'
            cur.execute(attache)
        conn.commit()
        cur = conn.execute(request, parameters)
        res = cur.fetchall()
    return res


def _prepare_tile_to_tile_request(coverage: float, tile_column: str, same_utm=True) -> T2TRequest:
    if coverage is None:
        logger.warning(
            "No minimum coverage defined in configuration, using {:.0%} as default coverage.".format(0.1))
        coverage = 0.1
    else:
        logging.debug("Using {:.0%} coverage.".format(coverage))
    # Open db
    select_l8tile_not_on_180th_meridian = SELECT_NOT_ON_180TH_MERIDIAN.format(
        geo_col='geometry', table='l8tiles.l8tiles')
    select_s2tile_not_on_180th_meridian = SELECT_NOT_ON_180TH_MERIDIAN.format(
        geo_col='geometry', table='s2tiles.s2tiles')

    sql_request = (
        f"SELECT "
        f"  s2.TILE_ID, "
        f"  l8.PATH_ROW, "
        f"  (st_area(st_intersection(l8.geometry, s2.geometry)) / st_area(s2.geometry)) as Coverage "
        f"FROM ({select_l8tile_not_on_180th_meridian}) as l8,"
        f"({select_s2tile_not_on_180th_meridian}) as s2 "
        f"WHERE {tile_column} == ? "
        f"AND Coverage >= ? "
        f"AND Coverage is not NULL "
    )

    if same_utm:
        sql_request+="AND cast(SUBSTR(s2.TILE_ID, 1, 2) as INTEGER ) == l8.UTM "

    return T2TRequest(coverage, sql_request)


def mgrs_to_wrs(mgrs_tile, coverage=None, same_utm=True):
    """Get WRS tiles that cover a MGRS by at least a coverage percentage.
    Result is sorted by coverage desc

    Args:
        mgrs_tile (str): MGRS tile id that should intersect WRS tiles to retrieve
        coverage (float): minimum coverage percentage of MGRS tile by WRS tile, default to 0.1

    Returns:
        A tuple of WRS [path,row] and the coverage of the MGRS tile, sorted by coverage
        Examples : ([45,56],45)
    """

    t2t_request = _prepare_tile_to_tile_request(coverage, "s2.TILE_ID", same_utm)

    data = _select_on_attache_db(
        {'l8tiles': _database_path(L8_TILE_DB), 's2tiles': _database_path(S2_TILE_DB)},
        t2t_request.sql_request,
        [mgrs_tile, t2t_request.coverage]
    )
    # Sort by coverage
    data = sorted(data, key=lambda t: t[2], reverse=True)
    result = [([int(i) for i in entry[1].split('_')], entry[2]) for entry in data]
    return result


def wrs_to_mgrs(wrs_path, coverage=None):
    """Get MGRS tiles for which a WRS tile cover at least the MGRS by a coverage percentage

    Args:
        wrs_path (str): WRS path row
        coverage (float): minimum MGRS percentage coverage by WRS tile

    Returns:
        Array of MGRS tile ids sorted by coverage desc
    """

    t2t_request = _prepare_tile_to_tile_request(coverage, "l8.PATH_ROW")

    data = _select_on_attache_db(
        {'l8tiles': _database_path(L8_TILE_DB), 's2tiles': _database_path(S2_TILE_DB)},
        t2t_request.sql_request,
        ["{}_{}".format(*wrs_path), t2t_request.coverage]
    )
    # Sort by coverage
    data = sorted(data, key=lambda t: t[2], reverse=True)
    result = [entry[0] for entry in data]
    return result


def get_coverage(wrs_path: tuple, mgrs_tile: str, same_utm=True) -> float:
    """Get the percentage coverage of an MGRS tile by WRS.
    If same_utm is True and wrs_path UTM does not match mgrs_tile UTM
    returned coverage will be 0.

    Args:
        wrs_path (tuple): tuple of WRS path and row
        mgrs_tile (str): MGRS tile id
        check_utm: shall search also check same UTM for matching WRS & MGRS tile

    Returns:
        Percentage of MGRS tile coverage by WRS, 0 if UTM does not match

    """
    # Open db
    print("wrs_path %s, same_utm %s", wrs_path, same_utm)
    coverage = 0
    select_l8tile_not_on_180th_meridian = SELECT_NOT_ON_180TH_MERIDIAN.format(
        geo_col='geometry', table='l8tiles.l8tiles')
    select_s2tile_not_on_180th_meridian = SELECT_NOT_ON_180TH_MERIDIAN.format(
        geo_col='geometry', table='s2tiles.s2tiles')

    sql_request = (
        f"SELECT "
        f"  (st_area(st_intersection(l8.geometry, s2.geometry)) / st_area(s2.geometry)) as Coverage "
        f"FROM ({select_l8tile_not_on_180th_meridian}) as l8,"
        f"({select_s2tile_not_on_180th_meridian}) as s2 "
        f"WHERE s2.TILE_ID == ? "
        f"AND l8.PATH_ROW == ? "
        f"AND Coverage is not NULL "
    )

    if same_utm:
        sql_request+="AND cast(SUBSTR(s2.TILE_ID, 1, 2) as INTEGER ) == l8.UTM "

    data = _select_on_attache_db(
        {'l8tiles': _database_path(L8_TILE_DB), 's2tiles': _database_path(S2_TILE_DB)},
        sql_request,
        # pylint: disable=consider-using-f-string
        [mgrs_tile, "{}_{}".format(*wrs_path)]
    )
    print("data: %s", data)
    if len(data) > 0:
        coverage = data[0][0]
    return coverage


def _select_tiles_by_spatial_relationships(relation, roi):
    """Retrieve MGRS tiles having the relation with a ROI.
    For now, exclude tiles having ids string with 01 or 60

    Args:
        roi (str): the ROI as WKT

    Returns:
        list of tile ids
    """
    with sqlite3.connect(_database_path(S2_TILE_DB)) as connection:
        logging.debug("ROI: %s", roi)
        connection.enable_load_extension(True)
        connection.load_extension("mod_spatialite")
        sql = f"select TILE_ID from s2tiles where {relation}(s2tiles.geometry, GeomFromText('{roi}'))==1"
        logging.debug("SQL request: %s", sql)
        cur = connection.execute(sql)
        # TODO: For now, first mgrs tile is excluded. To improve in a future version
        # TODO: Add coverage
        tiles = [tile[0] for tile in cur.fetchall() if not tile[0].startswith('01') and not tile[0].startswith('60')]
        logging.debug("Tiles: %s", tiles)
    return tiles


def tiles_intersect_roi(roi):
    """Retrieve MGRS tiles that intersect a ROI.
    For now, exclude tiles having ids string with 01 or 60

    Args:
        roi (str): the ROI as WKT

    Returns:
        list of tile ids

    """
    return _select_tiles_by_spatial_relationships("intersects", roi)


def tiles_contains_roi(roi):
    """Retrieve MGRS tiles that completely contained a ROI.
    For now, exclude tiles having ids string with 01 or 60

    Args:
        roi (str): the ROI as WKT

    Returns:
        list of tile ids

    """
    return _select_tiles_by_spatial_relationships("contains", roi)


def get_mgrs_def(tile: str) -> dict|None:
    """Get MGRS tile definition

    Args:
        tile (str): MGRS tile code

    Returns:
        dict|None: MGRS def having keys: 
        'index', 'TILE_ID', 'EPSG', 'UTM_WKT', 'MGRS_REF', 'LL_WKT', 'geometry'
        None if mgrs tile is not found
    """

    with sqlite3.connect(_database_path(S2_TILE_DB)) as connection:
        logging.debug("TILE: %s", tile)
        sql = f"select * from s2tiles where TILE_ID='{tile}'"
        logging.debug("SQL request: %s", sql)
        connection.row_factory = sqlite3.Row
        cur = connection.execute(sql)
        res = cur.fetchall()
        if len(res) > 0:
            return res[0]
        
        logging.error("tile %s not found in database", tile)
        return None


def mgrs_to_wkt(tile, utm=False):
    """Get the MGRS tile geom as WKT in LL or UTM.

    Args:
        tile (str): tile id
        utm (bool): if coordinates must be UTM or not

    Returns:
        tile geom as WKT or None if no tile match
    """
    with sqlite3.connect(_database_path(S2_TILE_DB)) as connection:
        logging.debug("TILE: %s", tile)
        sql = f"select {'UTM_WKT' if utm else 'LL_WKT'} from s2tiles where TILE_ID='{tile}'"
        logging.debug("SQL request: %s", sql)
        cur = connection.execute(sql)
        res = cur.fetchall()
        if len(res) > 0:
            wkt = res[0][0]
            logging.debug("TILE WKT: %s", wkt)
        else:
            wkt = None
            logging.error("tile %s not found in database", tile)
    return wkt


def wrs_to_wkt(wrs_id: str):
    """Get WRS tile geom as WKT

    Args:
        wrs_id (str): name of the WRS tile

    Returns:
        tile geom as WKT
    """
    with sqlite3.connect(_database_path("l8tiles.db")) as connection:
        logging.debug("WRS: %s", wrs_id)
        sql = f"select LL_WKT from l8tiles where PATH_ROW='{wrs_id}'"
        logging.debug("SQL request: %s", sql)
        cur = connection.execute(sql)
        wkt = cur.fetchall()[0][0]
        logging.debug("WRS WKT: %s", wkt)
    return wkt
