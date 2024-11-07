#!/bin/bash

# Colors for pretty output
GREEN='\033[0;32m'
BLUE='\033[0;34m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# Configuration
DATA=sample
LLM=gpt-4o-mini
GPUS=${GPUS:-0}  # Use GPUS from .env or default to 0
SYNONYM_THRESH=0.8
LLM_API=openai
RETRIEVER=colbertv2

# Function to show usage
usage() {
    echo -e "${BLUE}Usage: $0 [index|retrieve]${NC}"
    echo "  index    - Create ColBERT index for the sample corpus"
    echo "  retrieve - Run retrieval test on existing index"
    exit 1
}

# Check if command argument is provided
if [ $# -ne 1 ]; then
    usage
fi

# Change to HippoRAG directory
cd HippoRAG || {
    echo -e "${RED}Error: HippoRAG directory not found${NC}"
    exit 1
}

# Check if sample_corpus.json exists
if [ ! -f "data/sample_corpus.json" ]; then
    echo -e "${RED}Error: data/sample_corpus.json not found${NC}"
    exit 1
fi

case "$1" in
    "index")
        echo -e "${GREEN}Starting indexing process...${NC}"
        bash src/setup_hipporag_colbert.sh $DATA $LLM $GPUS $SYNONYM_THRESH $LLM_API
        ;;
    "retrieve")
        echo -e "${GREEN}Running retrieval test...${NC}"
        python3 src/ircot_hipporag.py \
            --dataset sample \
            --retriever $RETRIEVER \
            --llm openai \
            --llm_model $LLM \
            --max_steps 1 \
            --doc_ensemble f \
            --top_k 10 \
            --sim_threshold $SYNONYM_THRESH \
            --damping 0.5
        ;;
    *)
        usage
        ;;
esac

echo -e "${GREEN}Operation complete!${NC}"