FROM python:3.7.4-alpine
RUN apk add --no-cache git
WORKDIR /modmailbot
COPY . /modmailbot
RUN pip install --no-cache-dir -r requirements.min.txt
CMD ["python", "bot.py"]