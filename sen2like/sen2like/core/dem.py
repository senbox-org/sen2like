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

"""
Module to manage MGRS DEM file
"""

import logging
import os

logger = logging.getLogger("Sen2Like")


class DEMRepository:  # pylint: disable=too-few-public-methods
    """
    Access class to MGRS DEM files
    DEM files are store as {dem_folder}/{dem_dataset}/Copernicus_DSM_{resolution}m_{tilecode}.TIF
    """

    def __init__(self, dem_folder: str, dem_dataset: str, resolution: int):
        """Constructor

        Args:
            dem_folder (str): base DEM folder
            dem_dataset (str): dataset to use
            resolution (int): DEM resolution to use in DEM dataset
        """
        self.dataset_name = dem_dataset
        self._dem_path = os.path.join(dem_folder, dem_dataset)
        self._file_expr = f"Copernicus_DSM_{resolution}m_{{tilecode}}.TIF"

    def get_by_mgrs(self, mgrs_tile_code: str) -> str:
        """Get DEM file path for a MGRS tile

        Args:
            mgrs_tile_code (str): MGRS tile code.

        Raises:
            FileNotFoundError: if the DEM file does not exists in the DEM storage

        Returns:
            str: DEM file path
        """
        expected_file_name = self._file_expr.format(tilecode=mgrs_tile_code)
        expected_file_path = os.path.join(self._dem_path, expected_file_name)

        if not os.path.isfile(expected_file_path):
            logger.error("Cannot find %s", expected_file_path)
            raise FileNotFoundError(f"Cannot retrieve {expected_file_name} in {self._dem_path}")

        return expected_file_path
