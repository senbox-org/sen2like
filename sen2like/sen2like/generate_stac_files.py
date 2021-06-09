"""Generates stac files for old products found in specified product_path"""

import argparse
import glob
import os
import sys

import rasterio

from core.QI_MTD.stac_interface import STACWriter
from core.products.hls_product import S2L_HLS_Product

stats = {}


def write_tile_products(tile_path, dry_run=False, cog=False):
    print(tile_path)
    tile = os.path.basename(tile_path)
    stats[tile] = {"invalid": 0, "found": 0, "generated": 0}

    if not dry_run:
        stac_writer = STACWriter(os.path.join(tile_path, "catalog.json"), sid=f"Catalog for tile {tile}",
                                 title=f"{tile}", cog=cog)
    for product_path in glob.iglob(os.path.join(tile_path, '*')):
        if not os.path.isdir(product_path):
            continue
        print(f">> {product_path}")
        product = S2L_HLS_Product(product_path)
        if product.product is None:
            print("...Skipping")
            continue
        product.read_metadata()

        ql_name = glob.glob(os.path.join(os.path.dirname(product.mtl.tile_metadata), "QI_DATA", "*QL_B432.jpg"))

        stats[tile]['found'] += 1
        if dry_run:
            continue
        try:
            stac_writer.write_product(product, product.path, list(product.mtl.bands.values()),
                                      os.path.basename(ql_name[0]) if ql_name else "",
                                      product.mtl.granule_id)
        except rasterio.errors.RasterioIOError:
            print("Product uses old format... Skipping")
            stats[tile]['invalid'] += 1
        else:
            stats[tile]['generated'] += 1
    if not dry_run:
        stac_writer.write_catalog()
        return stac_writer


def print_stats():
    for tile in stats:
        print(f"\n{tile}")
        print(f"\t[{stats[tile]['found']} products found]")
        if not args.dry_run:
            print(f"\t[{stats[tile]['invalid']} products with old formats found]")
        print(f"\t[{stats[tile]['generated']} stac files generated]")


def main(args):
    if not args.dry_run:
        stac_writer = STACWriter(catalog_path=args.catalog_path, cog=args.cog, with_bbox=False)
        stac_writer.write_catalog()
    if args.is_tile:
        catalogs = [write_tile_products(args.path, args.dry_run, cog=args.cog)]
    else:
        catalogs = [write_tile_products(_tile_path, args.dry_run, cog=args.cog) for _tile_path in
                    sorted(glob.glob(os.path.join(args.path, '*'))) if os.path.isdir(_tile_path)]

    if not args.dry_run:
        for _catalog in catalogs:
            stac_writer.catalog.add_child(_catalog.catalog, title=_catalog.title)
        stac_writer.write_catalog()

    print_stats()


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument("path", help="Path where to search for products")
    parser.add_argument("--is-tile", help="Indicates if the path is a tile path", action='store_true', dest='is_tile')
    parser.add_argument("--catalog-path", "-c", help="Catalog path. If path does not exist it will be created",
                        required=False)
    parser.add_argument("--dry-run", help="Only list products. Do not generate files.", action='store_true')
    parser.add_argument("--cog", help="Set image assets type to COG", action='store_true')

    args = parser.parse_args()

    sys.exit(main(args))
