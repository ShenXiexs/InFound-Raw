import asyncio
from urllib.parse import quote_plus

import aio_pika

USERNAME = "<RABBITMQ_USER>"
PASSWORD = "<RABBITMQ_PASSWORD>"  # raw password before URL encoding
HOST = "<RABBITMQ_HOST>"
PORT = 5672
VHOST = "/<RABBITMQ_VHOST>"

encoded_pwd = quote_plus(PASSWORD)
AMQP_URL = f"amqp://{USERNAME}:{encoded_pwd}@{HOST}:{PORT}/{quote_plus(VHOST)}"


async def test_connection():
    try:
        print(f"Testing connection: {AMQP_URL}")
        connection = await aio_pika.connect_robust(AMQP_URL, timeout=30, heartbeat=60)
        print("✅ RabbitMQ connection succeeded!")
        await connection.close()
    except Exception as e:
        print(f"❌ Connection failed: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(test_connection())
