# docker image baser on miniconda image (debian:latest)
FROM continuumio/miniconda3

# install in curent docker image mesa-glx
RUN apt-get update && apt-get install -y libgl1-mesa-glx

# set the working dir to /usr/local/sen2like
WORKDIR /usr/local/sen2like

# Create the environment:
# copy requirements.txt from sources to docker image
COPY ./requirements.txt .
# create sen2like env from requirement
RUN conda create -n sen2like --file requirements.txt -c conda-forge

# copy script code to run when container is started:
COPY ./sen2like .

# set sne2like.py executable
RUN chmod +x /usr/local/sen2like/sen2like.py

# initialise conda for all shells
RUN conda init bash

# force activation of sen2like env on bash
RUN echo "conda activate sen2like" >> ~/.bashrc
