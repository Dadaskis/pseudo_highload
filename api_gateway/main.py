from fastapi import FastAPI
from contextlib import asynccontextmanager
from typing import MutableMapping
from aio_pika import Message, connect, Connection, Channel, Queue, Exchange, ExchangeType
import asyncio
import uuid

class MicroserviceRPCClient:
    connection: Connection
    channel: Channel
    callback_queue: Queue
    exchange: Exchange

    def __init__(self):
        self.futures: MutableMapping[str, asyncio.Future] = {}
    
    async def get_queue_safe(self, queue_name: str) -> Channel:
        queue = None
        try:
            queue = await self.channel.declare_queue(
                queue_name, durable=True, passive=False)
        except Exception as e:
            queue = await self.channel.declare_queue(
                queue_name, passive=True)
        return queue

    async def get_exchange_safe(
            self, exchange_name: str, exchange_type: ExchangeType) -> Exchange:
        exchange = None
        try:
            exchange = await self.channel.declare_exchange(
                exchange_name, exchange_type, durable=True, passive=False)
        except Exception as e:
            exchange = await self.channel.declare_exchange(
                exchange_name, exchange_type, passive=True)
        return exchange

    async def connect(self):
        self.connection = await connect("amqp://guest:guest@localhost/")
        self.channel = await self.connection.channel()
        self.callback_queue = await self.get_queue_safe("main_callback")
        await self.callback_queue.consume(self.on_response)
    
    async def on_response(self, message: Message):
        if message.correlation_id is None:
            print(f"Whoopsie doopsie the message is invalid: {message!r}")
            return
        if not self.futures.get(message.correlation_id):
            print(f"No {message.correlation_id} ID at futures")
            print(self.futures)
            return
        future: asyncio.Future
        future = self.futures.pop(message.correlation_id)
        future.set_result(message.body)
        await message.ack()
    
    async def call(self, message_text: str):
        correlation_id = str(uuid.uuid4())

        loop = asyncio.get_running_loop()
        future = loop.create_future()
        self.futures[correlation_id] = future

        await self.channel.default_exchange.publish(
            Message(
                message_text.encode(),
                content_type="text/plain",
                correlation_id=correlation_id,
                reply_to=self.callback_queue.name
            ),
            routing_key="main"
        )

        return await future

    async def close(self):
        await self.connection.close()

rpc = MicroserviceRPCClient()

async def app_startup():
    print("Backend start up!")
    await rpc.connect()

async def app_shutdown():
    print("Backend shutting down!")
    await rpc.close()

@asynccontextmanager
async def app_lifespan(api: FastAPI):
    await app_startup()
    yield
    await app_shutdown()

app = FastAPI(lifespan=app_lifespan)

@app.get("/")
async def root():
    result = await rpc.call("Tell yourself a story")
    return {"message": result}

@app.get("/health")
async def health():
    return {"status": "ok"}