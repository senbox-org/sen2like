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
KLT module.
Expose KLTMatcher, KTLResult, and klt_matcher_factory.
klt_matcher_factory keep a single (same) instance of KLTMatcher
"""

from .klt import KLTMatcher, KTLResult


class KLTMatcherFactory:
    # pylint: disable=too-few-public-methods
    """Factory that keep a single instance of KLTMatcher.
    It is recommended to use the module `klt_matcher_factory` instance of this class
    """

    klt_matcher: KLTMatcher | None = None

    def get_klt_matcher(self) -> KLTMatcher:
        """Provide a KLTMatcher

        Returns:
            KLTMatcher: matcher
        """
        if self.klt_matcher is None:
            self.klt_matcher = KLTMatcher()
        return self.klt_matcher


klt_matcher_factory = KLTMatcherFactory()

__all__ = [
    "KLTMatcher",
    "KTLResult",
    "klt_matcher_factory",
]
