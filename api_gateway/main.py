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
            2. Gets a "main_callback" queue.
            3. Registers a message callback at "main_callback".
        """
        self.connection = await connect("amqp://guest:guest@localhost/")
        self.channel = await self.connection.channel()
        self.callback_queue = await self.get_queue_safe("main_callback")
        await self.callback_queue.consume(self.on_response)
    
    async def on_response(self, message: Message):
        """
            Called on a new unprocessed message from "main_callback" queue.
            0. Checks if there's a correlation_id, if it is None - rejects the message entirely (no requeuing).
            1. Checks if there's a registered "future" promised value at self.futures.
               If there's none, rejects the message and requeues it.
               ...
               THIS is the part where I deeply regret that I didn't use Redis here.
               There are better solutions than doing what I do here, but it's such a clusterfuck to develop...
               In Redis you can just store the result by ID and then later get it.
               If you REALLY wonder what could've been done here, I'm just going to leave some code here.
            
               VARIANT 1 - Sharding.
                    ```
                    exchange = await channel.declare_exchange(
                        "user_tasks",
                        ExchangeType("x-consistent-hash"),
                        durable=True
                    )

                    queue1 = await channel.declare_queue("worker1", durable=True)
                    await queue1.bind(exchange, routing_key="0")

                    queue2 = await channel.declare_queue("worker2", durable=True)
                    await queue2.bind(exchange, routing_key="1")

                    await exchange.publish(
                        message,
                        routing_key=str(hash(user_id)) 
                    )
                    ```
               It's basically about making several queues, where different workers get their shit.
               Should I say that this implementation is just ATROCIOUS?

               Variant 2 - Dead Letter Exchange
                    ```
                    queue = await channel.declare_queue(
                        "main",
                        durable=True,
                        arguments={
                            "x-message-ttl": 60000,
                            "x-dead-letter-exchange": "dlx"
                        }
                    )

                    dlx = await channel.declare_exchange("dlx", ExchangeType.DIRECT)
                    dead_queue = await channel.declare_queue("main_dead", durable=True)
                    await dead_queue.bind(dlx, routing_key="main_dead")
                    ```
               Basically, the idea is simple, make a "Dead Letter Exchange" for those messages
               that you brutally reject with no requeuing. They end up in that pile of trash that
               you can later check. Okay, would YOU wanna iterate through million of those potential
               thrown-away letters? I would NOT.
            
               You know what they say, like, insanity is about repeating the same action over and over
               again thinking you will get any different results? So yeah, that's what I do with messages
               here, if it ain't fit I just put it back hoping the other workers will work with that.
               One of them will, but how many CPU time will we waste on the same message?
               ...
            ...
            Let's pretend I didn't turn this comment section into a confession.
            
            UPDATE: After testing that shit with "wrk" utility I managed to break it.
            It broke when there were 3 instances of that API gateway, but I'm not too surprised about that.
            You know what was *really* surprising? The fact that I managed to break it even with a single
            instance of that API gateway.
            That implementation sucks so hard I'll just go and use Redis, fuck that.

            ...
            2. Get a "future" promised value, put a result into it...
            3. Acknowledge the message :)
        """
        if message.correlation_id is None:
            print(f"Whoopsie doopsie the message is invalid: {message!r}")
            await message.reject(requeue=False)
            return
        if not self.futures.get(message.correlation_id):
            print(f"No {message.correlation_id} ID at futures")
            # print(self.futures)
            return_count = message.headers.get("return_counter", 0)
            if return_count > 10:
                await message.reject(requeue=False)
                return
            return_count += 1
            message.headers["return_counter"] = return_count
            await message.reject(requeue=True)
            return
        future: asyncio.Future
        future = self.futures.pop(message.correlation_id)
        future.set_result(message.body)
        await message.ack()
    
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
                reply_to=self.callback_queue.name
            ),
            routing_key="main"
        )

        return await future

    async def close(self):
        """
            Closes the RabbitMQ connection.
        """
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