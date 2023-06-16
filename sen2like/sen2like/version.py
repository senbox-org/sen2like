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

"""Version of the Application."""

__version__ = '4.3.0'

_splitted_version = __version__.split('.')

_major = f"{int(_splitted_version[0]):02d}"
_minor = f"{int(_splitted_version[1]):02d}"

# sample :
# version = 4.1.0 => 04.01 | 0401
# version = 4.12.0 => 04.12  | 0412
baseline_dotted = f"{_major}.{_minor}"
baseline = f"{_major}{_minor}"
