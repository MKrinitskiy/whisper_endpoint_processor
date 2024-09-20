FROM nvcr.io/nvidia/cuda:12.2.2-runtime-ubuntu22.04
# FROM nvcr.io/nvidia/pytorch:23.02-py3
# FROM nvcr.io/nvidia/pytorch:24.03-py3
# FROM python:3.8-slim
# FROM python:3.12-slim
# FROM mk/pytorch_2403:whisper

# USER    root

RUN set -eux && \
    apt update && \
    DEBIAN_FRONTEND="noninteractive" apt install -y software-properties-common && \
    add-apt-repository ppa:deadsnakes/ppa -y && \
    apt update && \
    DEBIAN_FRONTEND="noninteractive" apt install -y --no-install-recommends python3.8 python3.8-full python3.8-dev python3.8-distutils && \
    rm /usr/bin/python3 && \
    ln -s /usr/bin/python3.8 /usr/bin/python3 && \
    ln -s /usr/bin/python3.8 /usr/bin/python && \
    DEBIAN_FRONTEND="noninteractive" apt install -y --no-install-recommends \
        python3-pip cython3 python3-wheel tzdata ssh openssh-server build-essential \
        ffmpeg git vim sudo tmux wget curl unzip zip && \
    rm -rf /var/lib/apt/lists/*

RUN pip3 install -U pip && pip3 install -U wheel && pip3 install -U setuptools==59.5.0

COPY ./requirements.txt /tmp/requirements.txt
RUN pip install -r /tmp/requirements.txt && \
    rm -r /tmp/requirements.txt

WORKDIR /whisper
RUN git clone https://github.com/MahmoudAshraf97/whisper-diarization.git ./ && \
    pip install -r ./requirements.txt && \
    pip install huggingface_hub==0.22.0 && \
    pip install -U pydantic

WORKDIR /code

CMD ["bash"]
