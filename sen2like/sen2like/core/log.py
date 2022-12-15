# -*- coding: utf-8 -*-

"""This module contains configuration functions for the logging system."""

import logging
import os
import time

def configure_loggers(
    logger, log_path, is_debug, log_filename="sen2like.log", without_date=True
):
    """Define the global parameters for the logger output.

    :param log_path: The path where to store log files.
    :param is_debug: Activate debug logging flag.
    :param log_filename: The name of the logfile.
    :param without_date: Do no write date in log file.
    """
    if not os.path.exists(log_path):
        os.makedirs(log_path)

    logging.Formatter.converter = time.gmtime

    file_handler = logging.FileHandler(os.path.join(log_path, log_filename))

    date_format = "" if without_date else "%(asctime)s "

    level = logging.DEBUG if is_debug else logging.INFO

    logger.setLevel(level)

    log_format = f"[%(levelname)-8s] {date_format}- %(module)-20s - %(message)s"
    formatter = logging.Formatter(
        fmt=log_format,
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    file_handler.setFormatter(formatter)

    logging.basicConfig(
        level=level,
        format=log_format,
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    logger.addHandler(file_handler)
