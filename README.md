# Pseudo High-Load

Welcome to hell!

**Please, be advised it is just a prototype that was developed in a very limited span of time. There are still possible improvements.**

Test result on my machine
```
[dadaskis@Dadaskis api_gateway]$ wrk -t 12 -c 2400 -d 60 --timeout 6 http://localhost:80
Running 1m test @ http://localhost:80
  12 threads and 2400 connections
  Thread Stats   Avg      Stdev     Max   +/- Stdev
    Latency     5.06s    91.91ms   5.59s    92.17%
    Req/Sec    43.71     62.26   460.00     88.60%
  10833 requests in 1.00m, 2.23MB read
  Socket errors: connect 1391, read 0, write 0, timeout 1214
  Non-2xx or 3xx responses: 1214
Requests/sec:    180.43
Transfer/sec:     37.96KB
```

This is a demonstration of a "classic" high-load setup where an API endpoint performs a heavy operation (simulated 5-second processing) while handling concurrent requests. The system uses FastAPI as an API gateway, RabbitMQ for message queuing, and Redis for result storage, enabling horizontal scalability of the processing microservice.

## Architecture Overview

- **API Gateway** (`api_gateway/main.py`): FastAPI application that receives HTTP requests, publishes them to RabbitMQ, and waits for results via Redis Pub/Sub
- **Microservice** (`microservice/main.py`): Worker that consumes messages from RabbitMQ, simulates 5 seconds of processing, and publishes results to Redis
- **Redis**: Acts as a result store and notification system via Pub/Sub channels
- **RabbitMQ**: Message broker for distributing tasks to worker instances

When a request hits the gateway endpoint (`/`), it:
1. Generates a correlation ID
2. Publishes the task to the `main` RabbitMQ queue
3. Subscribes to Redis Pub/Sub channel for the result
4. Returns the result once available (or times out)

## Prerequisites

- Python 3.10 or higher
- RabbitMQ server
- Redis server
- Systemd (for running services)

## Arch Linux Setup

**Please, be advised - this is a minimalistic setup and I didn't really check it on my own. Production setup may differ, but this set of steps *supposedly* worked on my machine.**

### 1. Install Required Packages

```bash
sudo pacman -S python python-pip rabbitmq valkey nginx
```

### 2. Configure File Descriptor Limits

RabbitMQ, Redis, Nginx (especially Nginx) require sufficient file descriptors to handle concurrent connections. Add the following to `/etc/security/limits.conf`:

```bash
# Add these lines
* soft nofile 65536
* hard nofile 65536
root soft nofile 65536
root hard nofile 65536
```

For systemd services, override the limits in service files or add to `/etc/systemd/system.conf`:

```ini
DefaultLimitNOFILE=65536
```

After making changes, reboot or restart the user session.

### 3. Configure Nginx
Edit a configuration file `/etc/nginx/nginx.conf` with a following config:

```nginx
worker_processes  1;

error_log  logs/error.log;

include modules.d/*.conf;

worker_rlimit_nofile 128000;

events {
    worker_connections  4096; # Increase worker_connections to handle high load
}


http {
    include       mime.types;
    default_type  application/octet-stream;
    
    access_log  logs/access.log  main;

    sendfile        on;
    
    keepalive_timeout  65; # Necessary for high load too

    upstream fastapi_backend { # Create a new backend
        keepalive 128; # Necessary for high load
        
        # A bunch of addresses to different API gateways
        server 127.0.0.1:8000;
        server 127.0.0.1:8001;
        server 127.0.0.1:8002;
    }

    server {
        listen       80;
        server_name  localhost;

        access_log  logs/host.access.log  main;

        # 80th port root, it will redirect to API gateways
        location / {
            proxy_pass http://fastapi_backend; # Telling it to use our API gateways
            proxy_http_version 1.1;
            proxy_set_header Connection "";
            proxy_set_header Host $host;
            proxy_set_header X-Real-IP $remote_addr;
        }
        
        error_page   500 502 503 504  /50x.html;
        location = /50x.html {
            root   /usr/share/nginx/html;
        }
    }
}
```

### 4. Start and Enable Services

```bash
# Start RabbitMQ
sudo systemctl enable --now rabbitmq

# Start Redis
sudo systemctl enable --now valkey

# Start Nginx
sudo systemctl enable --now nginx
```

### 5. Verify Services

```bash
# Check RabbitMQ status (management plugin optional)
sudo rabbitmqctl status

# Check Redis status
redis-cli ping
# Should return PONG
```

### 6. Clone the Repository

```bash
git clone https://github.com/Dadaskis/pseudo_highload
cd pseudo_highload
```

### 7. Create Virtual Environment and Install Dependencies

```bash
python -m venv venv
source venv/bin/activate
pip install fastapi uvicorn aio-pika redis aiohttp
```

## Running the System

### Terminal 1: Start the Microservice

```bash
cd microservice
python main.py 1  # The number is the service ID for logging
```

### Terminal 2: Start the API Gateway

```bash
cd api_gateway
uvicorn main:app --host 0.0.0.0 --port 8000 --workers 1
```

### Terminal 3: Test the API

```bash
curl http://localhost:8000/
# Wait ~5 seconds, response: {"message":"Response for <uuid>"}

# Health check
curl http://localhost:8000/health
# Response: {"status":"ok"}
```

## Scaling the Microservice

To scale horizontally, simply start additional instances:

```bash
# Terminal 1
cd api_gateway
uvicorn main:app --host 0.0.0.0 --port 8000 --workers 1

# Terminal 2
cd api_gateway
uvicorn main:app --host 0.0.0.0 --port 8001 --workers 1

# Terminal 3
cd api_gateway
uvicorn main:app --host 0.0.0.0 --port 8002 --workers 1

# Terminal 3
cd microservice
for i in {1..300}; do python main.py ${i} & done
```

RabbitMQ will distribute messages across all available consumers. The prefetch count is set to 50, allowing each worker to process up to 50 messages concurrently.

## Load Testing

The included `client_highload_test` script is for reference only (I liked that failed attempt too much to remove it). For proper load testing, use `wrk`:

```bash
# Install wrk AUR (using yay)
yay -S wrk

# Run load test (12 threads, 1000 connections, 30 seconds)
# 80th port is Nginx load balancing requests between multiple API gateways (check Nginx configuration section)
wrk -t 12 -c 1000 -d 30s --timeout 6s http://localhost:80/
```

## Configuration

### RabbitMQ Connection
Default: `amqp://guest:guest@localhost/`

### Redis Connection
Default: `localhost:6379`

### Queue Names
- **Task Queue**: `main`
- **Result Pub/Sub Channel**: `results`
- **Result Keys**: `result:{correlation_id}` (TTL: 60 seconds)

### Microservice Settings
- **Prefetch Count**: 50 messages per worker
- **Processing Time**: 5 seconds (simulated)
- **Message Expiration**: 6 seconds

### API Gateway Settings
- **RPC Timeout**: 7 seconds
- **Port**: 8000

## File Structure

```
pseudo_highload/
├── api_gateway/
│   └── main.py          # FastAPI gateway, RPC client
├── microservice/
│   └── main.py          # Worker that processes tasks
├── client_highload_test/
│   └── main.py          # Reference load test (not recommended)
├── _line_counter.py     # Utility to analyze repository
├── README.md
└── .gitignore
```

## Troubleshooting

### Connection Refused Errors

Ensure RabbitMQ and Redis are running:
```bash
sudo systemctl status rabbitmq redis
```

### File Descriptor Limits

Check current limits:
```bash
ulimit -n
# Should show 65536
```

Check RabbitMQ file descriptors:
```bash
sudo rabbitmqctl status | grep file_descriptors
```

### Redis Pub/Sub Not Working

Verify Redis is configured correctly:
```bash
redis-cli INFO stats | grep pubsub
```

### High Load Simulation Issues

The included Python client has limitations. Use `wrk` or `hey` for accurate load testing:
```bash
# Alternative: hey (install from AUR)
hey -n 1000 -c 100 http://localhost:8000/
```

## License

MIT License. *Happiness to everyone!*