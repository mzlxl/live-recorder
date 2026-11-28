FROM python:3.12-slim-bookworm
WORKDIR /opt/recorder
ARG DEBIAN_MIRROR=https://deb.debian.org
RUN sed -i "s|http://deb.debian.org|$DEBIAN_MIRROR|g" /etc/apt/sources.list.d/debian.sources \
    && apt-get -o Acquire::Retries=3 update \
    && apt-get -o Acquire::Retries=3 install -y --no-install-recommends \
    ca-certificates chromium ffmpeg fonts-wqy-zenhei libgomp1 \
    && rm -rf /var/lib/apt/lists/*
COPY requirements.txt .
ARG PIP_INDEX_URL=https://pypi.org/simple
RUN pip install --no-cache-dir -r requirements.txt pywhispercpp==1.5.1
COPY app app
COPY web web
COPY config.py run.py ./
ENV TZ=Asia/Shanghai OPENBLAS_NUM_THREADS=1 RECORDER_HOST=0.0.0.0 RECORDER_BROWSER=/usr/bin/chromium \
    RECORDER_WHISPER_CPP_MODEL=/models/ggml-small-q5_1.bin
EXPOSE 8000
CMD ["python", "run.py"]
