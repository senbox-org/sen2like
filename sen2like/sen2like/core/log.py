# -*- coding: utf-8 -*-

"""This module contains configuration functions for the logging system."""

import logging
import os


def configure_loggers(log_path, is_debug, log_filename="sen2like.log", without_date=True):
    """Define the global parameters for the logger output.

        :param log_path: The path where to store log files.
        :param is_debug: Activate debug logging flag.
        :param log_filename: The name of the logfile.
        :param without_date: Do no write date in log file.
    """
    if not os.path.exists(log_path):
        os.makedirs(log_path)
    file_handler = logging.FileHandler(os.path.join(log_path, log_filename))
    console_handler = logging.StreamHandler()
    date_format = "" if without_date else "%(asctime)s "
    logging.basicConfig(level=logging.DEBUG if is_debug else logging.INFO,
                        format='[%(levelname)-8s] {}- %(module)-20s - %(message)s'.format(date_format),
                        datefmt="%Y-%m-%d %H:%M:%S", handlers=[file_handler, console_handler])
