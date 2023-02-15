import sqlite3
from collections import OrderedDict
from math import floor

import pandas as pd
from pykml import parser
import argparse


def readDescription(des):
    """
    read kml description and derive a dictionary
    with key/value for each parameters
    (expected keys: ['UTM_WKT', 'EPSG', 'TILE_ID', 'LL_WKT', 'MGRS_REF'])
    """

    # read string stream
    lines = []
    line = ''
    isText = False
    for c in des:
        if c == '<':
            isText = False
            if line.strip() != '':
                lines.append(line)
            line = ''
        if isText:
            line += c
        if c == '>':
            isText = True

    # fill dictionary
    meta = {}
    for i in range(0, len(lines), 2):
        meta[lines[i]] = lines[i + 1]

    # return dictionary
    return meta


def main():
    args_parser = argparse.ArgumentParser(formatter_class=argparse.RawTextHelpFormatter)
    args_parser.add_argument(
        'kml_file',
        help=('KML can be downloaded on Landsat website: '
              'https://www.usgs.gov/media/files/landsat-wrs-2-scene-boundaries-kml-file'))
    args_parser.add_argument(
        'utm_file',
        help=('''CSV file having path_row/utm table, formatted as path,row,utm, example :
              1,1,31
              1,2,30
              1,3,29
              1,4,28'''))
    args_parser.add_argument('-o', '--out', help='Out database', default='l8tiles.db', required=False)
    args = args_parser.parse_args()

    # load path_row / utm zone mapping
    path_row_map = {}
    with open(args.utm_file) as path_rwo_utm_file:
        for line in path_rwo_utm_file:
            split = line.strip().split(",")
            path_row_map[f"{split[0]}_{split[1]}"] = int(split[2])

    with open(args.kml_file) as f:
        root = parser.parse(f).getroot()

    print('nb tiles:', len(root.Document.Placemark))

    # create empty dic with keys
    dic = OrderedDict()

    # now for each tile
    for pm in root.Document.Placemark[0:]:
        meta = {'WRS_ID': pm.name.text}
        # get tileid and description
        [path, row] = meta['WRS_ID'].split('_')
        meta['PATH'] = path
        meta['ROW'] = row
        coords_txt = pm.Polygon.outerBoundaryIs.LinearRing.coordinates.text.strip()

        coords = []
        for coord in coords_txt.split(' '):
            coords.append(" ".join(coord.split(',')[:2]))  # keeping x,y removing z

        ll_wkt = "MULTIPOLYGON(((" + ",".join(coords) + ")))"
        meta['LL_WKT'] = ll_wkt
        """print path, row
        print coords
        print ll_wkt"""

        # set utm
        meta['UTM'] = path_row_map[meta['WRS_ID']]

        # get key/values pairs from kml description
        for key in ['WRS_ID', 'PATH', 'ROW', 'LL_WKT', 'UTM']:
            if key not in list(dic.keys()):
                # init list
                dic[key] = []
            # add values
            dic[key].append(meta[key])

    df = pd.DataFrame.from_dict(dic)
    conn = sqlite3.connect(args.out)
    conn.enable_load_extension(True)
    conn.load_extension("mod_spatialite")

    conn.execute("SELECT InitSpatialMetaData();")

    create_req = (
        "CREATE TABLE l8tiles ("
        "PATH_ROW VARCHAR(7), PATH VARCHAR(3), ROW VARCHAR(3), LL_WKT VARCHAR, UTM INTEGER); "
    )
    conn.execute(create_req)

    conn.execute("SELECT AddGeometryColumn('l8tiles', 'geometry', 4326, 'POLYGON', 0);")

    insert_req = (
        "INSERT INTO l8tiles(PATH_ROW, PATH, ROW, LL_WKT, geometry, UTM) "
        "VALUES (?, ?, ?, ?, GeomFromText(?, 4326), ?) "
    )
    values = []
    for _, row in df.iterrows():
        coord = ((row['LL_WKT'].split('('))[3]).split(')')[0]
        values.append((
            row['WRS_ID'],
            row['PATH'],
            row['ROW'],
            row['LL_WKT'],
            f'POLYGON(({coord}))',
            row['UTM']))
    conn.executemany(insert_req, values)
    conn.commit()
    conn.close()

    print('OK')


if __name__ == '__main__':
    main()
