from aio_pika import Message, connect, Connection, Channel, Queue, Exchange, ExchangeType, IncomingMessage
import asyncio

connection: Connection
channel: Channel
queue: Queue
exchange: Exchange

async def get_queue_safe(channel: Channel, queue_name: str):
    queue = None
    try:
        queue = await channel.declare_queue(queue_name, durable=True, passive=False)
    except Exception as e:
        queue = await channel.declare_queue(queue_name, passive=True)
    return queue

async def get_exchange_safe(
        channel: Channel, exchange_name: str, exchange_type: ExchangeType):
    exchange = None
    try:
        exchange = await channel.declare_exchange(
            exchange_name, exchange_type, durable=True, passive=False)
    except Exception as e:
        exchange = await channel.declare_exchange(
            exchange_name, exchange_type, passive=True)
    return exchange

async def on_message(message: IncomingMessage):
    global channel
    print(f"Received message: {message}")
    print(f"Received message body: {message.body}")
    print("Before sleep...")
    await asyncio.sleep(5.0)
    print("After sleep...")
    message_text = f"Response for {message.correlation_id}"
    await channel.default_exchange.publish(
        Message(
            message_text.encode(),
            correlation_id=message.correlation_id
        ),
        routing_key=message.reply_to
    )
    await message.ack()

async def main():
    global connection, channel, queue
    print("Backend start up!")
    
    connection = await connect("amqp://guest:guest@localhost/")
    async with connection:
        channel = await connection.channel()
        queue = await get_queue_safe(channel, "main")
        await queue.consume(on_message)
        print("Waiting for the messages from the future")
        await asyncio.Future()

if __name__ == "__main__":
    asyncio.run(main())