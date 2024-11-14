from pathlib import Path
from documents import process_documents

DATA_DIR = Path("./data")


def main():
    chunks = process_documents(DATA_DIR)
    print(f"Processed {len(chunks)} chunks")

if __name__ == "__main__":
    main()