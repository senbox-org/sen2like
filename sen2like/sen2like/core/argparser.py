"""
Module to manage S2L arguments
"""
import os
from argparse import ArgumentParser
from dataclasses import dataclass
from datetime import datetime
from version import __version__


def _get_date(date_str: str) -> datetime:
    return datetime.strptime(date_str, "%Y-%m-%d") if date_str else date_str


@dataclass
class DateRange:
    """A simple date range container
    """
    start_date: datetime = None
    end_date: datetime = None


# pylint: disable=too-few-public-methods
class Mode:
    """program mode constants
    """
    SINGLE_TILE = 'single-tile-mode'
    MULTI_TILE = 'multi-tile-mode'
    PRODUCT = 'product-mode'
    ROI_BASED = 'roi-based-mode'


class S2LArgumentParser(ArgumentParser):
    """ArgumentParser inheritance that configure S2L argument parser
    """

    def __init__(self, config_dir: str):
        """Init and configure S2LArgumentParser

        Args:
            config_dir (str): default conf dir path

        """

        super().__init__()
        self._config_dir = config_dir
        self._configure_arguments()
        self._args = None

    def parse_args(self, args=None, namespace=None):
        self._args = super().parse_args(args, namespace)
        return self._args

    def get_date_range(self) -> DateRange:
        """get start/end date from arguments

        Returns:
            DateRange: initialized 'DateRange' if possible or empty 'DateRange' (with None values)
        """
        if self._args.operational_mode in [Mode.SINGLE_TILE, Mode.MULTI_TILE, Mode.ROI_BASED]:
            start_date = _get_date(self._args.start_date)
            end_date = _get_date(self._args.end_date)
            return DateRange(start_date, end_date)

        # empty range
        return DateRange()

    def _configure_arguments(self):
        """Configure this parser with common arguments and 4 subparser
        (product-mode, single-tile-mode, multi-tile-mode, roi-based-mode)
        subparser have specific and common arguments

        """

        # use parser_class=ArgumentParser avoid error on subparsers.add_parser
        # see https://stackoverflow.com/questions/47833828/subparsers-add-parser-typeerror-init-got-an-unexpected-keyword-argument
        subparsers = self.add_subparsers(dest='operational_mode', help="Operational mode", parser_class=ArgumentParser)
        self._add_common_arguments(self)

        # Product mode arguments
        sp_product = subparsers.add_parser(Mode.PRODUCT, help="Process a single product")
        sp_product.add_argument('product', help="Landsat8 L1 product path / or Sentinel2 L1C product path")
        self._add_common_arguments(sp_product)
        sp_product.add_argument("--tile", help="Id of the MGRS tile to process", required=True)

        # Single tile mode arguments
        sp_single_tile_mode = subparsers.add_parser(Mode.SINGLE_TILE, help='Process all products on a MGRS tile')
        sp_single_tile_mode.add_argument("tile", help="Id of the MGRS tile to process")
        # self._add_tile_arguments(sp_single_tile_mode)
        self._add_tile_mode_arguments(sp_single_tile_mode)
        self._add_common_arguments(sp_single_tile_mode)

        # Multi tile mode arguments
        sp_multi_tile_mode = subparsers.add_parser(Mode.MULTI_TILE, help='Process all products on a ROI')
        sp_multi_tile_mode.add_argument("roi", help="Json file containing the ROI to process")
        self._add_tile_mode_arguments(sp_multi_tile_mode)
        sp_multi_tile_mode.add_argument("--jobs", "-j", dest="jobs", help="Number of tile to process in parallel",
                                        default=None)
        self._add_common_arguments(sp_multi_tile_mode)

        # ROI based mode arguments
        roi_based_mode = subparsers.add_parser(
            Mode.ROI_BASED,
            help='Process all products that fully contains an ROI. The ROI footprint must be FULLY INSIDE a MGRS tile.')
        roi_based_mode.add_argument("roi", help="Json file containing the ROI to process")
        roi_based_mode.add_argument(
            "--tile",
            help="MGRS Tile Code : Force Processing of a specific tile in case several MGRS tiles contain the ROI footprint",
            required=False)
        self._add_tile_mode_arguments(roi_based_mode)
        self._add_common_arguments(roi_based_mode)

    def _add_common_arguments(self, parser: ArgumentParser):
        """Add common arguments to the given parser

        Args:
            parser (ArgumentParser): parser to add arguments to

        """

        parser.add_argument('--version', '-v', action='version', version='%(prog)s ' + __version__)
        parser.add_argument("--refImage", dest="refImage", type=str,
                            help="Reference image (use as geometric reference)", metavar="PATH", default=None)
        parser.add_argument("--wd", dest="wd", type=str,
                            help="Working directory (default : /data/production/wd)", metavar="PATH",
                            default='/data/production/wd')
        parser.add_argument("--conf", dest="S2L_configfile", type=str,
                            help="S2L_configuration file (Default: SEN2LIKE_DIR/conf/S2L_config.ini)", metavar="PATH",
                            default=os.path.join(self._config_dir, '..', 'conf', 'config.ini'))
        parser.add_argument("--confParams", dest="confParams", type=str,
                            help='Overload parameter values (Default: None). '
                                 'Given as a "key=value" comma-separated list. '
                                 'Example: --confParams "doNbar=False,doSbaf=False"',
                            metavar="STRLIST", default=None)
        parser.add_argument("--bands", dest="bands", type=lambda s: [i for i in s.split(',')],
                            help="S2 bands to process as coma separated list (Default: ALL bands)", metavar="STRLIST",
                            default=None)
        parser.add_argument("--allow-other-srs", dest="allow_other_srs",
                            help="Selected product to process can have another SRS/UTM than the one of the S2 tile (default: False)", action="store_true")
        parser.add_argument("--no-run", dest="no_run", action="store_true",
                            help="Do not start process and only list products (default: False)")
        parser.add_argument("--intermediate-products", dest="generate_intermediate_products", action="store_true",
                            help="Generate intermediate products (default: False)")
        parser.add_argument("--parallelize-bands", action="store_true",
                            help="Process bands in parallel (default: False)")
        debug_group = parser.add_argument_group('Debug arguments')
        debug_group.add_argument("--debug", "-d", dest="debug", action="store_true",
                                 help="Enable Debug mode (default: False)")
        debug_group.add_argument("--no-log-date", dest="no_log_date", action="store_true",
                                 help="Do no store date in log (default: False)")

    @staticmethod
    def _add_tile_mode_arguments(parser: ArgumentParser):
        """Add arguments for *-tile-mode parser, aka start-date, end-date and l2a

        Args:
            parser (ArgumentParser): parser to add arguments

        """
        parser.add_argument("--start-date", dest="start_date",
                            help="Beginning of period (format YYYY-MM-DD)",
                            default='')
        parser.add_argument("--end-date", dest="end_date", help="End of period (format YYYY-MM-DD)",
                            default='')
        parser.add_argument("--l2a", help="Processing level Level-2A for S2 products if set (default: L1C)",
                            action='store_true')
