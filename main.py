from documents import process_documents
from shared_resources import DATA_DIR


def main():
    chunks = process_documents(DATA_DIR)
    print(f"Processed {len(chunks)} chunks")

if __name__ == "__main__":
    main()