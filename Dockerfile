FROM python:3.11-alpine as base

RUN apk add --no-cache \
    # cairosvg dependencies
    cairo-dev cairo cairo-tools \
    # pillow dependencies
    jpeg-dev zlib-dev \
    && adduser -D -h /home/modmail -g 'Modmail' modmail

ENV VIRTUAL_ENV=/home/modmail/.venv
ENV PATH="$VIRTUAL_ENV/bin:$PATH"

WORKDIR /home/modmail

FROM base as builder

RUN apk add build-base libffi-dev

RUN python -m venv $VIRTUAL_ENV

COPY --chown=modmail:modmail requirements.txt .
RUN pip install --upgrade pip setuptools && \
    pip install -r requirements.txt

FROM base as runtime

# copy the entire venv
COPY --from=builder --chown=modmail:modmail $VIRTUAL_ENV $VIRTUAL_ENV

# copy repository files
COPY --chown=modmail:modmail . .

# this disables the internal auto-update
ENV USING_DOCKER yes

USER modmail

CMD ["python", "bot.py"]
