from fastapi import FastAPI
from contextlib import asynccontextmanager
from aio_pika import Message, Connection, Channel, Queue, connect

app = FastAPI()

connection: Connection = None
channel: Channel = None
queue: Queue = None

async def app_startup():
    print("Backend start up!")
    global connection, channel, queue
    connection = await connect("amqp://guest:guest@localhost/")
    async with connection:
        channel = await connection.channel()
        queue = await channel.declare_queue("main")

async def app_shutdown():
    print("Backend shutting down!")
    await connection.close()

@asynccontextmanager
async def app_lifespan(api: FastAPI):
    await app_startup()
    yield
    await app_shutdown()

@app.get("/")
async def root():
    global connection, channel, queue
    async with connection:
        await channel.default_exchange.publish(
            Message(b"Tell yourself a story"),
            routing_key=queue.name
        )
    return {"message": "Welcome to Nowhere"}