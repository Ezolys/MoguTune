# 
FROM python:3.14-slim-bookworm

# 
WORKDIR /code

# 
RUN apt-get update \
&& apt-get install -y --no-install-recommends git \
&& apt-get purge -y --auto-remove \
&& rm -rf /var/lib/apt/lists/*

# 
COPY ./requirements.txt /code/requirements.txt

# 
RUN pip install --no-cache-dir --upgrade -r /code/requirements.txt

# 
COPY introqbot/*.py /code/introqbot/
COPY introqbot/cogs/commands/*.py /code/introqbot/cogs/commands/
COPY introqbot/locales/*.json /code/introqbot/locales/
COPY pyproject.toml /code/

# 
CMD ["python", "/code/src/main.py"]
