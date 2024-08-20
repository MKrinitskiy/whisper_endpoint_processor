FROM nvcr.io/nvidia/pytorch:24.03-py3
# FROM python:3.8-slim
# FROM mk/pytorch_2403:whisper

USER    root
RUN \
    set -eux; \
    apt-get update; \
    DEBIAN_FRONTEND="noninteractive" apt-get install -y --no-install-recommends \
    build-essential \
    ffmpeg \
    git \
    vim \
    sudo \
    tmux \
    wget \
    curl \
    unzip \
    zip \
    ; \
    rm -rf /var/lib/apt/lists/*

RUN pip3 install -U pip && pip3 install -U wheel && pip3 install -U setuptools==59.5.0

COPY ./requirements.txt /tmp/requirements.txt
RUN pip install -r /tmp/requirements.txt && rm -r /tmp/requirements.txt

WORKDIR /code

CMD ["bash"]
