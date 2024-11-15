from api_queue import start_api_queue, stop_api_queue
from documents import process_documents
from shared_resources import DATA_DIR, logger
import asyncio


async def main():
    await start_api_queue()
    chunks = await process_documents(DATA_DIR)
    await stop_api_queue()

if __name__ == "__main__":
    asyncio.run(main())