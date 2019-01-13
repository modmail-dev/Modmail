import os 

from sanic import Sanic, response
from motor.motor_asyncio import AsyncIOMotorClient
import aiohttp

from core.models import LogEntry 

app = Sanic(__name__)

@app.listener('before_server_start')
async def init(app, loop):
    app.db = AsyncIOMotorClient(os.getenv('MONGO_URI')).modmail

app.get('/')
async def index(request):
    return response.json('Welcome!')

@app.get('/<key>')
async def getlogsfile(request, key):
    log = await app.db.logs.find_one({'key': key})

    if log is None:
        return response.text('Not Found', status=404)
    else:
        return response.text(str(LogEntry(log)))

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=os.getenv('PORT'))