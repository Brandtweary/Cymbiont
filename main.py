from documents import process_documents
from shared_resources import DATA_DIR, logger


def main():
    chunks = process_documents(DATA_DIR)

if __name__ == "__main__":
    main()