# docker image baser on miniconda image (debian:latest)
FROM continuumio/miniconda3:22.11.1 AS build
LABEL stage=sen2like_build

# set the working dir to /usr/local/sen2like
WORKDIR /usr/local/sen2like

# Create the environment:
# copy requirements.txt from sources to docker image
COPY ./requirements.txt .
# create sen2like env from requirement
RUN conda create -n sen2like --file requirements.txt -c conda-forge

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
RUN apt-get update && apt-get install -y libgl1-mesa-glx

# set PATH with venv
ENV VIRTUAL_ENV=/venv
ENV PATH="$VIRTUAL_ENV/bin:$PATH"

# set the working dir to /usr/local/sen2like
WORKDIR /usr/local/sen2like

# copy script code to run when container is started:
COPY ./sen2like .

# set sen2like.py executable
RUN chmod +x /usr/local/sen2like/sen2like.py

ENTRYPOINT ["./sen2like.py"]
