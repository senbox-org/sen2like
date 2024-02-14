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
ARG SEN2LIKE_BUILD_IMAGE_TAG
# docker image baser on miniconda image (debian:latest)
FROM ${SEN2LIKE_BUILD_IMAGE_TAG} AS build
LABEL stage=sen2like_build

# set the working dir to /usr/local/sen2like
WORKDIR /usr/local/sen2like

# Install conda-pack:
RUN conda install -c conda-forge conda-pack

# Use conda-pack to create a standalone enviornment
# in /venv:
RUN conda-pack -n sen2like -o /tmp/env.tar && \
  mkdir /venv && cd /venv && tar xf /tmp/env.tar && \
  rm /tmp/env.tar

# We've put venv in same path it'll be in final image,
# so now fix up paths:
RUN /venv/bin/conda-unpack

# FINAL IMAGE
FROM debian:bullseye-slim AS runtime

# Copy /venv from the previous stage:
COPY --from=build /venv /venv

# install in curent docker image mesa-glx
RUN apt-get update \
  && apt-get install -y libgl1-mesa-glx \
  && rm -rf /var/lib/apt/lists/*

# set PATH with venv
ENV VIRTUAL_ENV=/venv
ENV PATH="$VIRTUAL_ENV/bin:$PATH"
ENV PROJ_LIB=/venv/share/proj

# set the working dir to /usr/local/aux_data
WORKDIR /usr/local/aux_data
COPY ./aux_data .

# set the working dir to /usr/local/sen2like
WORKDIR /usr/local/sen2like

# copy script code to run when container is started:
COPY ./sen2like .

# set sen2like.py executable
RUN chmod +x /usr/local/sen2like/sen2like.py

ENTRYPOINT ["./sen2like.py"]
