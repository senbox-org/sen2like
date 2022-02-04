"""Generates stac files for old products found in specified product_path"""

import argparse
import glob
import os
import sys

import rasterio

from core.QI_MTD.stac_interface import STACWriter, S2LSTACCatalog, S2LSTACCatalog_Tile, S2LSTACCatalog_Product
from core.products.hls_product import S2L_HLS_Product

stats = {}


def print_stats():
    for tile in stats:
        print(f"\n{tile}")
        print(f"\t[{stats[tile]['found']} products found]")
        if not args.dry_run:
            print(f"\t[{stats[tile]['invalid']} products with old formats found]")
        print(f"\t[{stats[tile]['generated']} stac files generated]")


def main(args):
    catalog_dir = os.path.abspath(args.catalog_dir)
    s2l_out = os.path.abspath(args.s2l_out)
    catalog = S2LSTACCatalog()

    for tile_path in glob.glob(os.path.join(s2l_out, '*')):
        if not os.path.isdir(tile_path):
            continue
        tile = os.path.basename(tile_path)
        stats[tile] = {"invalid": 0, "found": 0, "generated": 0}
        collections = S2LSTACCatalog_Tile(tile, tile)
        for product_path in sorted(
                glob.glob(os.path.join(tile_path, '*')), key=lambda x: x[len(tile_path) + 12: len(tile_path) + 27]):
            if not os.path.isdir(product_path):
                continue
            print(f">> {product_path}")
            product = S2L_HLS_Product(product_path)
            if product.product is None:
                print("...Skipping")
                continue
            product.read_metadata()

            ql_name = glob.glob(os.path.join(os.path.dirname(product.mtl.tile_metadata), "QI_DATA", "*QL_B432.jpg"))
            product_url = args.s2l_out_url + '/' + os.path.relpath(product_path, s2l_out)
            for b in product.mtl.bands.keys():
                ref_band = b
                break

            stats[tile]['found'] += 1
            try:
                item = S2LSTACCatalog_Product(product, product_url, ref_band, cog=args.cog)
                item.add_product_bands_asset()
                item.add_quicklook_asset(product.mtl.granule_id, os.path.basename(ql_name[0]))
                collections.add_item(item, item.id)
            except rasterio.errors.RasterioIOError:
                print("Product uses old format... Skipping")
                stats[tile]['invalid'] += 1
            else:
                stats[tile]['generated'] += 1
        collections.update_extent_from_items()
        catalog.add_child(collections, title=collections.title)

    if not args.dry_run:
        catalog.write_catalog(catalog_dir, args.catalog_dir_url)

    print_stats()


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument("catalog_dir", help="Path to catalog output directory")
    parser.add_argument(
        "catalog_dir_url",
        help="The base url call by stac client to get catalog directory "
             "(exemple: if calalog url is http://sen2like.com/stac/catalog.json, the base url is http://sen2like.com/stac)")
    parser.add_argument("s2l_out", help="The sen2like output directory")
    parser.add_argument("s2l_out_url", help="The base url to accesse to the sen2like output directory")


    # parser.add_argument("--is-tile", help="Indicates if the path is a tile path", action='store_true', dest='is_tile')
    parser.add_argument("--dry-run", help="Only list products. Do not generate files.", action='store_true')
    parser.add_argument("--cog", help="Set image assets type to COG", action='store_true')

    args = parser.parse_args()

    sys.exit(main(args))
