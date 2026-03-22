# Okay, so, the idea of a microservice... It's basically just a program that you can place on any server
# hardware, it will somehow get the data from a message broker, process it, somehow return the result.
# It's a very simplified description, I know. The main point is writing a piece of software that allows
# to be horizontally scaled, I mean, that's the entire logic behind high-load if we take fundamentals.
#
# So, what does this one "microservice" do?
# ---
# main() - A starting point
# 0. Connects to RabbitMQ
# 1. Listens to "main" RabbitMQ queue
# 2. Loves the "main" RabbitMQ queue
# 3. Does "await asyncio.Future()" so the program enters the "eternal sleep" in the main() coroutine
#    ^^^ This is a shitty trick and isn't a graceful shutdown in any meaningful way...
#        But hey, I took that from aio_pika tutorial and it works here :)
#        If I would have to work further on that program, I'd rather make a proper shutdown logic, though.
# ---
# on_message() - Processing
# 0. Get the message from "main" queue
# 1. Sleep for 5 seconds... I mean... Act like you are doing meaningful work, oh yeah.
# 2. Publish the response to "main_callback" (it's written to "reply_to" anyway)
# 3. Acknowledge the message, it's important
# ---
# 
# By the way, this microservice is a RPC server. And I find it funny that it is easier to write a RPC server
# than a RPC client. Either way, if anything, I would rather make a RPC server read from RabbitMQ and post
# all the results to Radis or something. I didn't want to bring Radis into this repo, because I wanted to
# fool around with RabbitMQ. But, yeah, if I'd be working on something real, I'd rather use Redis. I love Redis.
#
# And yeah, this thing is not using REST API because we need asynchronous communication with actual possibility
# for seamless scalability. So, in this case, message brokens (like Kafka or RabbitMQ) for the win.
#
# Also I know RPC kinda sucks (especially this one RabbitMQ implementation), but I decided to make it here still.
# Mostly because it would be a really nice practice with RabbitMQ.

# Importing the stuff we really, really need.
from aio_pika import \
        Message, connect, Connection, \
            Channel, Queue, Exchange, \
                ExchangeType, IncomingMessage
from redis import asyncio as aioredis
from aiormq.exceptions import ChannelNotFoundEntity
import asyncio
import sys

# Just basic RabbitMQ stuff
connection: Connection
channel: Channel
queue: Queue

# Holy Redis
redis_con: aioredis.Redis

service_id = 0

try:
    service_id = sys.argv[1]
except Exception as ex:
    print("No service ID!")

async def get_queue_safe(channel: Channel, queue_name: str) -> Queue:
    """
        This function allows you to safely get a named RabbitMQ queue.
        If a queue doesn't exist - it makes a new one.
        If a queue does exist - it returns the one that exists.
        
        Arguments:
            channel - A RabbitMQ channel to create a queue.
            queue_name - A name for this queue.

        Returns:
            A glorified RabbitMQ queue.
    """
    queue = None
    
    try:
        # Assuming this is an existing queue...
        queue = await channel.declare_queue(queue_name, durable=True, passive=False)
    except ChannelNotFoundEntity as e:
        # ... and if it is not, we get an exception, catch it, make a new queue...
        queue = await channel.declare_queue(queue_name, passive=True)
    
    return queue

async def get_exchange_safe(
        channel: Channel, exchange_name: str, exchange_type: ExchangeType) -> Exchange:
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
        exchange = await channel.declare_exchange(
            exchange_name, exchange_type, durable=True, passive=False)
    except ChannelNotFoundEntity as e:
        # ... and here we realize it wasn't existing exchange, because the house
        # was lit up on fire and now we need to do that the other fancy way.
        exchange = await channel.declare_exchange(
            exchange_name, exchange_type, passive=True)
    
    return exchange

async def on_message(message: IncomingMessage):
    """
        Here we get all the messages sent over "main" queue!
        
        What it does is sleeping for 5 seconds and *then* publishing a message
        through default exchange of our channel, where it returns a simple text
        like "Response for {ID}".

        Arguments:
            message - An incoming message.
        
        Returns:
            Nothing.
    """
    global redis_con, service_id

    print(f"Service {service_id} processing {message.correlation_id}")

    await asyncio.sleep(5.0)
    message_text = f"Response for {message.correlation_id}"

    """
    # This is the old way.
    # Let's say "goodbye" to the old way.
    # Fuck you, the old way, we never liked you.
    await channel.default_exchange.publish(
        Message(
            message_text.encode(),
            correlation_id=message.correlation_id
        ),
        routing_key=message.reply_to
    )
    """

    await redis_con.setex(f"result:{message.correlation_id}", 60, message_text)
    await redis_con.publish("results", message.correlation_id)

    print(f"Service {service_id} published results of {message.correlation_id}")

    await message.ack()

async def main():
    """
        Main function is the entry point for this program.
        It has basic RabbitMQ initialization logic, and when everything has been setup,
        it just enters a sleeping state with "await asyncio.Future()"
    """
    global connection, channel, queue, redis_con, service_id
    print(f"Backend start up - {service_id}!")
    
    connection = await connect("amqp://guest:guest@localhost/")
    redis_con = aioredis.Redis(host="localhost", port=6379, decode_responses=True)
    
    async with connection:
        channel = await connection.channel()

        # Setting QOS to process only fifty at the time.
        # If the currently processed message was acknowledged,
        # only then we get a new message from the queue.
        await channel.set_qos(prefetch_count=50)

        queue = await get_queue_safe(channel, "main")
        await queue.consume(on_message)
        print(f"Waiting for the messages from the future - {service_id}")

        # TODO: Rewrite this to a somewhat graceful shutdown.
        # For now it just makes the "main()" coroutine sleep forever.
        await asyncio.Future()

if __name__ == "__main__":
    asyncio.run(main())