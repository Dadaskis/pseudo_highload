from fastapi import FastAPI
from contextlib import asynccontextmanager
from aio_pika import Message, connect, Connection, Channel, Queue
import asyncio

connection: Connection = None
channel: Channel = None
queue: Queue = None

async def get_a_damn_queue(queue_name):
    queue = None
    try:
        queue = await channel.declare_queue(queue_name, durable=True, passive=False)
    except Exception as e:
        queue = await channel.declare_queue(queue_name, passive=True)
    return queue

async def app_startup():
    global connection, channel, queue
    print("Backend start up!")
    
    connection = await connect("amqp://guest:guest@localhost/")
    channel = await connection.channel()
    queue = await get_a_damn_queue("main")

async def app_shutdown():
    global connection
    print("Backend shutting down!")
    await connection.close()

@asynccontextmanager
async def app_lifespan(api: FastAPI):
    await app_startup()
    yield
    await app_shutdown()

app = FastAPI(lifespan=app_lifespan)

@app.get("/")
async def root():
    global channel, queue
    
    await channel.default_exchange.publish(
        Message(b"Tell yourself a story"),
        routing_key=queue.name
    )
    
    return {"message": "Welcome to Nowhere"}

@app.get("/health")
async def health():
    return {"status": "ok"}