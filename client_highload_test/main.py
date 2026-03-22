"""
    A simple script that floods http://localhost:80/ with a TON of requests.
    Just makes a million of requests as fast as possible.
    ... or not a million...

    UPDATE: So, I wouldn't recommend you to use this thing. It's not a good way to simulate a lot of requests.
    It can do maximum of 479 valid requests and others get lost due to variety of errors.
    "wrk" utility does a much better job at simulating a lot of connections:
        wrk -t 12 -c 1000 -d 30s --timeout 6s http://localhost:80/
"""

from aiohttp import ClientSession, TCPConnector
import asyncio
import sys

SESSIONS_AMOUNT = 10

successful_requests = 0
sessions = []
session_id = 0

async def initialize_sessions_pool():
    global sessions
    connector = TCPConnector(limit=None)
    sessions = [
        ClientSession("http://localhost:80/", connector=connector) \
            for i in range(SESSIONS_AMOUNT)
    ]

async def close_sessions_pool():
    global sessions
    for session in sessions:
        await session.close()

async def get_session():
    global sessions, session_id
    session_id = (session_id + 1) % SESSIONS_AMOUNT
    return sessions[session_id]

async def send_request(request_id: int):
    global successful_requests
    try:
        print(f"Sending a request {request_id}")
        custom_headers = {
            "User-Agent" : f"aiohttp_client{request_id}"
        }
        session = await get_session()
        async with session.get("/") as response:
            print(f"Request ID processed {request_id} {await response.text()}")
            successful_requests += 1
    except Exception as ex:
        print(f"Something went wrong during the request {request_id}: {ex}")

async def main():
    try:
        value = int(sys.argv[1])
    except Exception as ex:
        print("You need to enter amount of requests to be sent by this test.")
        quit(0)
    print("Let the stress-test commence!")
    await initialize_sessions_pool()
    async with asyncio.TaskGroup() as group:
        tasks = [group.create_task(send_request(i)) for i in range(int(sys.argv[1]))]
    print(f"Successful requests: {successful_requests}")
    await close_sessions_pool()

asyncio.run(main())