from documents import process_documents
from shared_resources import DATA_DIR, logger
import asyncio


async def main():
    chunks = await process_documents(DATA_DIR)

if __name__ == "__main__":
    asyncio.run(main())