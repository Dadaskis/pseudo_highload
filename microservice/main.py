from aio_pika import Message, connect, Connection, Channel, Queue
from aio_pika.abc import AbstractIncomingMessage
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

async def on_message(message: AbstractIncomingMessage):
    print(f"Received message: {message}")
    print(f"Received message body: {message.body}")
    print("Before sleep...")
    await asyncio.sleep(5.0)
    print("After sleep...")

async def main():
    global connection, channel, queue
    print("Backend start up!")
    
    connection = await connect("amqp://guest:guest@localhost/")
    async with connection:
        channel = await connection.channel()
        queue = await get_a_damn_queue("main")
        await queue.consume(on_message, no_ack=True)
        print("Waiting for the messages from the future")
        await asyncio.Future()

if __name__ == "__main__":
    asyncio.run(main())