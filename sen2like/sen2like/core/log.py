# -*- coding: utf-8 -*-
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

    date_format = "" if without_date else "%(asctime)s | "

    level = logging.DEBUG if is_debug else logging.INFO

    logger.setLevel(level)

    log_format = f"{date_format}P-%(process)d | T-%(thread)-5d | %(levelname)-8s | %(module)-20s - %(message)s"
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
