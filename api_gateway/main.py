# The main API gateway. Man, that sounds very, very serious! Okay, let's break it down to simple parts.
# Firstly, as it is an API gateway, it has a REST API supported with FastAPI. Secondly, it is also
# a RPC client (where the entire logic is put into MicroserviceRPCClient) that communicates with
# all microservices that are "listening" to the "main" RabbitMQ queue. The sole purpose of this
# entire thing is to call microservices and... that's kinda it.
#
# So, the idea: You just call "http://localhost:8000/", and then, you wait for 5 seconds, processing that
# spicy, complicated operation that your mobile application needs, and then, it gets a message from
# the microservice that processed the request, it gets the response from a RabbitMQ queue called
# "main_callback", then you get a JSON as a result that contains some complicated data that takes
# whole damn 5 seconds to process on some server located at India. God, I love high-load.

# Importing all kinds of stuff.
# Yeah, you needed that comment to understand that.
from fastapi import FastAPI
from contextlib import asynccontextmanager
from typing import MutableMapping
from aio_pika import \
        Message, connect, Connection,\
                Channel, Queue, Exchange, ExchangeType
from redis import asyncio as aioredis
from datetime import timedelta
import asyncio
import uuid

class MicroserviceRPCClient:
    """
        A microservice RPC client.
        Or, in other words, a RPC client class built specifically to communicate with that one
        microservice that our project has.

        Example use:
        ```
        rpc = MicroserviceRPCClient()
        await rpc.connect()
        response = await rpc.call("Message from the future!")
        print(response) # Why not?
        await rpc.close()
        ```
    """

    connection: Connection
    channel: Channel
    callback_queue: Queue
    exchange: Exchange
    redis: aioredis.Redis
    pubsub: aioredis.client.PubSub
    pubsub_task: asyncio.Task

    def __init__(self):
        """
            Initializes this object, just adds self.futures hashmap.
        """
        self.futures: MutableMapping[str, asyncio.Future] = {}
    
    async def get_queue_safe(self, queue_name: str) -> Queue:
        """
            This function allows you to safely get a named RabbitMQ queue.
            If a queue doesn't exist - it makes a new one.
            If a queue does exist - it returns the one that exists.
            
            Arguments:
                queue_name - A name for this queue.

            Returns:
                A glorified RabbitMQ queue.
        """
        queue = None
        try:
            # Assuming this is an existing queue...
            queue = await self.channel.declare_queue(
                queue_name, durable=True, passive=False)
        except Exception as e:
            # ... and if it is not, we get an exception, catch it, make a new queue...
            queue = await self.channel.declare_queue(
                queue_name, passive=True)
        return queue

    async def get_exchange_safe(
            self, exchange_name: str, exchange_type: ExchangeType) -> Exchange:
        """
            This function allows you to safely get a named RabbitMQ exchange.
            If an exchange doesn't exist - it makes a new one.
            If an exchange does exist - it returns the one that exists.

            [WARNING]
            If you will try to get an existing exchange 
            whose exchange_type is different - you will get an exception.

            Arguments:
                channel - A RabbitMQ channel to create an exchange.
                exchange_name - A name for this exchange.
                exchange_type - A type of this exchange, can be DIRECT, FANOUT, TOPIC, HEADERS.

            Returns:
                A RabbitMQ exchange.
        """
        exchange = None
        try:
            # Here we assume that this is an existing exchange...
            exchange = await self.channel.declare_exchange(
                exchange_name, exchange_type, durable=True, passive=False)
        except Exception as e:
            # ... and here we realize it wasn't existing exchange, because the house
            # was lit up on fire and now we need to do that the other fancy way.
            exchange = await self.channel.declare_exchange(
                exchange_name, exchange_type, passive=True)
        return exchange

    async def connect(self):
        """
            A RabbitMQ initialization logic.
            0. Connects to "amqp://guest:guest@localhost/".
            1. Gets a channel.
            2. Initializes Redis
            3. Subscribes to Redis pubsub called "results"
        """
        self.connection = await connect("amqp://guest:guest@localhost/")
        self.channel = await self.connection.channel()
        self.redis = aioredis.Redis(host="localhost", port=6379, decode_responses=True)
        self.pubsub = self.redis.pubsub()
        await self.pubsub.subscribe("results")
        self.pubsub_task = asyncio.create_task(self.listen_to_pubsub())
    
    async def listen_to_pubsub(self):
        """
            Listens to Redis' PubSub called "results", if there's a value we are looking for,
            it sets it to appropriate "future" promised value and then it gets returned.
            Everyone are happy. Nobody remembers about the RabbitMQ catastrophe.
        """
        async for message in self.pubsub.listen():
            if message["type"] == "message":
                correlation_id = message["data"]
                future = self.futures.pop(correlation_id, None)
                if future and not future.done():
                    result = await self.redis.get(f"result:{correlation_id}")
                    if result:
                        future.set_result(result)
    
    async def call(self, message_text: str):
        """
            Calls the microservice with "message_text" as a message body.
            Simple as that, yeah!
        """
        correlation_id = str(uuid.uuid4())

        loop = asyncio.get_running_loop()
        future = loop.create_future()
        self.futures[correlation_id] = future

        await self.channel.default_exchange.publish(
            Message(
                message_text.encode(),
                content_type="text/plain",
                correlation_id=correlation_id,
                expiration=timedelta(seconds=6)
            ),
            routing_key="main"
        )

        return await asyncio.wait_for(future, timeout=7)

    async def close(self):
        """
            Closes the RabbitMQ connection.
        """
        await self.connection.close()
        await self.redis.close()

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