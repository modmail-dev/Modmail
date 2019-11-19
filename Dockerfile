FROM python:3.7.4-alpine
WORKDIR /modmailbot
COPY . /modmailbot
RUN pip install --no-cache-dir -r requirements.min.txt
CMD ["python", "bot.py"]