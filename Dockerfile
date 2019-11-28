FROM python:3.8-alpine
WORKDIR /modmailbot
COPY . /modmailbot
RUN  export PIP_NO_CACHE_DIR=false \
    && apk update \
    && apk add --update --no-cache --virtual .build-deps alpine-sdk \
    && pip install pipenv \
    && pipenv install --deploy --ignore-pipfile \
    && apk del .build-deps
CMD ["pipenv", "run", "bot"]