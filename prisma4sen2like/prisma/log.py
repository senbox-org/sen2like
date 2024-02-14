# -*- coding: utf-8 -*-
# Copyright (c) 2023 ESA.
#
# This file is part of Prisma4sen2like.
# See https://github.com/senbox-org/sen2like/prisma4sen2like for further info.
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


"""logging config module."""
import logging
import logging.config
import time


# Configure logging with UTC date
# https://docs.python.org/3.7/howto/logging-cookbook.html#formatting-times-using-utc-gmt-via-configuration
class UTCLoggingFormatter(logging.Formatter):
    """'logging.Formatter' to have utc date in log."""

    converter = time.gmtime


_LOG_FORMAT = "[%(levelname)-7s] [%(asctime)s] %(module)s.%(name)-10s - %(message)s"
_LOG_CONFIG = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "utc": {
            "()": UTCLoggingFormatter,
            "format": _LOG_FORMAT,
            "datefmt": "%Y-%m-%d %H:%M:%S",
        }
    },
    "handlers": {
        "console": {"class": "logging.StreamHandler", "formatter": "utc"},
        # "rotating_to_file": {
        #     "class": "logging.handlers.RotatingFileHandler",
        #     "formatter": "utc",
        #     "filename": "app.log",
        #     "maxBytes": 1024 * 1024,  # 1MB
        #     "backupCount": 10,
        # },
    },
    "root": {
        "handlers": [
            "console",
            # "rotating_to_file"
        ],
        "level": "INFO",
    },
}


def configure_logging(debug: bool, log_in_file: bool, log_file_path: str = ""):
    """Configure logger with the given log level.

    Args:
      level(str): logging level

    """
    level = logging.DEBUG if debug else logging.INFO

    _LOG_CONFIG["root"]["level"] = level

    if log_in_file:
        _LOG_CONFIG["handlers"]["rotating_to_file"] = {
            "class": "logging.handlers.RotatingFileHandler",
            "formatter": "utc",
            "filename": log_file_path,
            "maxBytes": 1024 * 1024,  # 1MB
            "backupCount": 10,
        }
        _LOG_CONFIG["root"]["handlers"].append("rotating_to_file")

    logging.config.dictConfig(_LOG_CONFIG)
