FROM python:3.13-slim-bookworm

WORKDIR /code

COPY ./requirements.txt /code/requirements.txt
COPY core/ /code/core/

RUN pip install --no-cache-dir --upgrade -r /code/requirements.txt

COPY main.py /code/main.py
COPY mogutune/*.py /code/mogutune/
COPY mogutune/cogs/commands/*.py /code/mogutune/cogs/commands/
COPY mogutune/quiz/*.py /code/mogutune/quiz/
COPY pyproject.toml /code/

CMD ["python", "/code/main.py"]
