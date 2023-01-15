from flask import Flask
from threading import Thread

app = Flask(__name__)

@app.route('/')
def main():
    return "<code>This is webserver for modmail bot hosted on replit.<br>Guide: <a href='https://go.anondev.ml/modmail-replit' target='__blank'>go.anondev.ml/modmail-replit</a></code>"

def run():
    app.run(host="0.0.0.0", port=8080)

def keep_alive():
    server = Thread(target=run)
    server.start()

keep_alive()