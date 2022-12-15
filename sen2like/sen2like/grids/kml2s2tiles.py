import sqlite3
from collections import OrderedDict

import pandas as pd
from pykml import parser
import argparse


def readDescription(pm):
    """
    read kml description and derive a dictionary
    with key/value for each parameters
    (expected keys: ['UTM_WKT', 'EPSG', 'TILE_ID', 'LL_WKT', 'MGRS_REF'])
    """

    # read string stream
    lines = []
    line = ''
    isText = False
    des = pm.description.text
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
        help=('S2 mgrs grid KML, can be downloaded on ESA website: \n'
              'https://sentinel.esa.int/documents/247904/1955685/S2A_OPER_GIP_TILPAR_MPC__20151209T095117_V20150622T000000_21000101T000000_B00.kml'))
    args_parser.add_argument('-o', '--out', help='Out database', default='s2tiles.db', required=False)
    args = args_parser.parse_args()
    with open(args.kml_file) as f:
        root = parser.parse(f).getroot()

    print('nb tiles:', len(root.Document.Folder.Placemark))
    # create empty dic with keys
    dic = OrderedDict()

    # now for each tile
    for pm in root.Document.Folder.Placemark[0:]:
        # get key/values pairs from kml description
        meta = readDescription(pm)
        for key in ['TILE_ID', 'EPSG', 'UTM_WKT', 'MGRS_REF', 'LL_WKT']:
            if key not in list(dic.keys()):
                # init list
                dic[key] = []
            # add values
            dic[key].append(meta[key])

    df = pd.DataFrame.from_dict(dic)
    conn = sqlite3.connect(args.out)
    conn.enable_load_extension(True)
    conn.load_extension("mod_spatialite")
    create_req = (
        "CREATE TABLE s2tiles ("
        "TILE_ID VARCHAR(5), EPSG VARCHAR(5), UTM_WKT VARCHAR, MGRS_REF VARCHAR, LL_WKT VARCHAR, geometry POLYGON); "
    )
    conn.execute(create_req)
    insert_req = (
        "INSERT INTO s2tiles(TILE_ID , EPSG , UTM_WKT , MGRS_REF , LL_WKT , geometry) "
        "VALUES (?, ?, ?, ?, ?, GeomFromText(?, 4326)) "
    )
    values = []
    for _, row in df.iterrows():
        coord = ((row['LL_WKT'].split('('))[3]).split(')')[0]
        values.append((
            row['TILE_ID'],
            row['EPSG'],
            row['UTM_WKT'],
            row['MGRS_REF'],
            row['LL_WKT'],
            f'POLYGON(({coord}))'))
    conn.executemany(insert_req, values)
    conn.commit()
    conn.close()

    print('OK')


if __name__ == '__main__':
    main()
