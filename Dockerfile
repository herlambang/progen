FROM python:3.10.3

ENV HOME=/usr/local/lib

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=off \
    PIP_DISABLE_PIP_VERSION_CHECK=on \
    PIP_DEFAULT_TIMEOUT=100

RUN curl -sSL https://raw.githubusercontent.com/python-poetry/poetry/master/get-poetry.py | python

ENV PATH=$HOME/.poetry/bin:$PATH

WORKDIR /app

COPY . .

CMD ["python", "/app/gen.py"]
