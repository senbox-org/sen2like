import sqlite3
from collections import OrderedDict

import pandas as pd

from .grids import GridsConverter

"""
### REQUIRES: ###
### TO ADD THIS CODE IN THE CLASS GridsConverter (grids.py) ###



from shapely.wkt import loads



   def _get_l8tiles(self):
        return pd.read_sql_query("SELECT * FROM l8tiles", self.conn)

    def close(self):
        self.conn.close()

    def getOverlaps(self, tilecode, minCoverage=0):
        #TODO: optimize because it is too slow. (Precompute for all S2 tiles? Use geodatabase like spatialite?)
        #TODO: should overlap only on same UTM zone
        # get mgrs info for tilecode
        mgrsinfo = self._get_roi(tilecode)
        wkt1 = mgrsinfo['LL_WKT'].item()
        g1 = loads(wkt1)
        if not g1.is_valid:
            print "Polygon geometry is not valid for tile {}".format(tilecode)
            return None

        res = []
        l8tiles = self._get_l8tiles()
        for index, row in l8tiles.iterrows():
            wkt2 = row['LL_WKT']
            g2 = loads(wkt2)
            if g2.intersects(g1):
                if not g2.is_valid:
                    print "Polygon geometry is not valid for tile {}".format(row['WRS_ID'])
                else:
                    coverage = 100 * g2.intersection(g1).area / g1.area
                    if coverage >= minCoverage:
                        res.append((row['WRS_ID'], row['PATH'], row['ROW'], coverage))
        return res

"""

# init grids converter
converter = GridsConverter()

dic = OrderedDict()
dic['TILE_ID'] = []
dic['WRS_ID'] = []
dic['Coverage'] = []

df = pd.read_sql_query('SELECT TILE_ID FROM s2tiles', converter.conn)
tilecodes = df['TILE_ID'].tolist()

for tilecode in tilecodes:
    print(tilecode)
    # get WRS tiles that overlaps
    res = converter.getOverlaps(tilecode)
    for r in res:
        dic['TILE_ID'].append(tilecode)
        dic['WRS_ID'].append(r[0])
        dic['Coverage'].append(r[3])

# close DB
converter.close()

# to pandas
df = pd.DataFrame.from_dict(dic)
dic = None

# to sql
conn = sqlite3.connect('l8_s2_coverage.db')
df.to_sql('l8_s2_coverage', conn)
conn.close()
