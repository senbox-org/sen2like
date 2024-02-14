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
PROVIDE `create_process_block` function which is dedicated to `S2L_Process` concrete class instance
It Exposes `S2L_Process` and `create_process_block`
"""


from core.dem import DEMRepository
from core.S2L_config import S2L_Config, config
from klt import klt_matcher_factory

from .S2L_Atmcor import S2L_Atmcor
from .S2L_Fusion import S2L_Fusion
from .S2L_Geometry import S2L_Geometry
from .S2L_GeometryCheck import S2L_GeometryCheck
from .S2L_InterCalibration import S2L_InterCalibration
from .S2L_Nbar import S2L_Nbar
from .S2L_PackagerL2F import S2L_PackagerL2F
from .S2L_PackagerL2H import S2L_PackagerL2H
from .S2L_Process import S2L_Process
from .S2L_Sbaf import S2L_Sbaf
from .S2L_Stitching import S2L_Stitching
from .S2L_Toa import S2L_Toa
from .S2L_TopographicCorrection import S2L_TopographicCorrection

_class_lookup = {
    S2L_Atmcor.__name__: S2L_Atmcor,
    S2L_Fusion.__name__: S2L_Fusion,
    S2L_InterCalibration.__name__: S2L_InterCalibration,
    S2L_Nbar.__name__: S2L_Nbar,
    S2L_PackagerL2F.__name__: S2L_PackagerL2F,
    S2L_PackagerL2H.__name__: S2L_PackagerL2H,
    S2L_Stitching.__name__: S2L_Stitching,
    S2L_Toa.__name__: S2L_Toa,
}


# DEFINE CUSTOM BUILDER FUNCTIONS HERE


def _create_topographic_correction(configuration: S2L_Config) -> S2L_TopographicCorrection:
    dem_repository = DEMRepository(
        configuration.get("dem_folder"),
        configuration.get("dem_dataset"),
        int(configuration.get("src_dem_resolution")),
    )

    topo_corr_limit = configuration.getfloat("topographic_correction_limiter")
    if not topo_corr_limit:
        raise RuntimeError(f"Configuration parameter {topo_corr_limit} not set in config file.")

    generate_intermediate_products = configuration.getboolean("generate_intermediate_products")
    apply_valid_pixel_mask = configuration.getboolean("apply_valid_pixel_mask")
    return S2L_TopographicCorrection(
        dem_repository, topo_corr_limit, apply_valid_pixel_mask, generate_intermediate_products
    )


def _create_geometry(configuration: S2L_Config) -> S2L_Geometry:
    return S2L_Geometry(
        klt_matcher_factory.get_klt_matcher(),
        configuration.getboolean("force_geometric_correction"),
        configuration.getboolean("doMatchingCorrection"),
        configuration.get("reference_band", "B04"),
        configuration.getboolean("generate_intermediate_products"),
    )


def _create_geometry_check(configuration: S2L_Config) -> S2L_GeometryCheck:
    return S2L_GeometryCheck(
        klt_matcher_factory.get_klt_matcher(),
        configuration.get("doAssessGeometry", default="").split(","),
        configuration.get("reference_band"),
        configuration.getboolean("generate_intermediate_products"),
    )


def _create_sbaf(configuration: S2L_Config) -> S2L_Sbaf:
    return S2L_Sbaf(
        configuration.getboolean("adaptative"),
        configuration.get("adaptative_band_candidates", default="").split(","),
        configuration.getboolean("generate_intermediate_products"),
    )


# CUSTOM BUILDER FUNCTIONS LOOKUP TABLE

_create_function_lookup = {
    S2L_Geometry.__name__: _create_geometry,
    S2L_GeometryCheck.__name__: _create_geometry_check,
    S2L_Sbaf.__name__: _create_sbaf,
    S2L_TopographicCorrection.__name__: _create_topographic_correction,
}


def create_process_block(process_name: str) -> S2L_Process:
    """Create a processing block instance.

    Args:
        process_name (str): name of the processing block to create

    Returns:
        S2L_Process: concrete `S2L_Process`
    """

    # get S2L_Process create function, if not found try using default constructor
    create_function = _create_function_lookup.get(process_name, None)

    # Try to use default constructor.
    if not create_function:
        create_function = _class_lookup.get(process_name, None)
        # Manual check to raise if process_name not declared in both lookup dict
        if not create_function:
            # this is a code engineering / chair keyboard interface error
            raise RuntimeError(
                f"Create function for processing block '{process_name}' not found in '_class_lookup' or '_create_function_lookup'."
            )

        return create_function(config.getboolean("generate_intermediate_products"))

    # call custom create function with config
    return create_function(config)


__all__ = ["create_process_block", "S2L_Process"]
