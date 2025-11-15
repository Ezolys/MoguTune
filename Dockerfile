FROM python:3.13-slim-bookworm

WORKDIR /code

RUN apt-get update \
&& apt-get install -y --no-install-recommends git \
&& apt-get purge -y --auto-remove \
&& rm -rf /var/lib/apt/lists/*

COPY ./requirements.txt /code/requirements.txt

RUN pip install --no-cache-dir --upgrade -r /code/requirements.txt

COPY main.py /code/main.py
COPY introqbot/*.py /code/introqbot/
COPY introqbot/cogs/commands/*.py /code/introqbot/cogs/commands/
COPY introqbot/resources/locales/*.json /code/introqbot/resources/locales/
COPY pyproject.toml /code/

CMD ["python", "/code/main.py"]
