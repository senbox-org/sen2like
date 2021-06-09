import sqlite3

import pandas as pd

conn1 = sqlite3.connect('s2grid.db')
conn2 = sqlite3.connect('../core/product_archive/data/l8_s2_coverage.db')

df = pd.read_sql_query('SELECT WRS_ID FROM l8tiles', conn1)
list_wrs = df['WRS_ID'].tolist()

# parse db
print('parse db')
dataframes = []
count = 0
n = len(list_wrs)
for i, wrs_id in enumerate(list_wrs):
    print(i, n)
    # get utm
    df = pd.read_sql_query(f'SELECT UTM FROM l8tiles WHERE WRS_ID=="{wrs_id}"', conn1)
    utm = int(df['UTM'])

    # get l8_s2_coverage on this wrs id
    df = pd.read_sql_query(f'SELECT * FROM l8_s2_coverage WHERE WRS_ID=="{wrs_id}"', conn2)

    # keep only tile with same utm
    df = df[df['TILE_ID'].str.startswith(f'{utm}')]
    dataframes.append(df)
    """count += 1
    if count == 10:
        break"""

# close input database
conn1.close()
conn2.close()

# concat, sort, clean
print('concat')
df = pd.concat(dataframes)
df.sort_values(by='TILE_ID', axis=0, inplace=True)
df.drop(columns=['index'], inplace=True)
df.reset_index(inplace=True, drop=True)

# to sql
print('write new db')
conn = sqlite3.connect('../core/product_archive/data/l8_s2_coverage_new.db')
df.to_sql('l8_s2_coverage', conn)
conn.close()
