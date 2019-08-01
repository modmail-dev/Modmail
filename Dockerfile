FROM library/python:latest
RUN apt update && apt install -y pipenv
RUN mkdir -p /bot && cd /bot && git clone https://github.com/kyb3r/modmail .
WORKDIR /bot
RUN pipenv install

CMD ["pipenv", "run", "python3", "bot.py"]
