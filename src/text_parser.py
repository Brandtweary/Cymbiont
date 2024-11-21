import re
from typing import List, Optional
from custom_dataclasses import Chunk
from pathlib import Path
from shared_resources import DATA_DIR, logger
from utils import get_paths


def is_header(text: str) -> bool:
    """Determine if a paragraph is a header based on word count per line and ending."""
    lines = [line.strip() for line in text.split('\n') if line.strip()]
    
    # Not a header if too many lines
    MAX_HEADER_LINES = 5
    if len(lines) > MAX_HEADER_LINES:
        return False
    
    # Check each line individually
    for line in lines:
        if len(line.split()) >= 10 or (line.endswith('.') and not line.endswith('Ph.D.')):
            return False
    
    return True

def combine_headers(paragraphs: List[str]) -> List[str]:
    """Combine headers with their following paragraphs, preserving line breaks."""
    result: List[str] = []
    header_buffer: List[str] = []
    
    for para in paragraphs:
        if is_header(para):
            header_buffer.append(para)
        else:
            if header_buffer:
                # Combine all headers with the current paragraph using line breaks
                result.append('\n'.join(header_buffer + [para]))
                header_buffer.clear()
            else:
                result.append(para)
    
    # Handle any remaining headers at the end of the text
    if header_buffer:
        result.append('\n'.join(header_buffer))
        
    return result

def extract_reference_numbers(text: str) -> set[str]:
    """Extract reference numbers from a paragraph's citations."""
    return set(re.findall(r'\[(\d+)\]', text))

def is_reference(text: str) -> bool:
    """Determine if a paragraph is a reference based on bracket notation."""
    text = text.strip()
    # Look for [N] at the start where N is a number
    return bool(re.match(r'^\[\d+\]', text))

def get_reference_number(text: str) -> str:
    """Extract the reference number from a reference paragraph."""
    match = re.match(r'^\[(\d+)\]', text.strip())
    return match.group(1) if match else ''

def combine_references(paragraphs: List[str]) -> List[str]:
    """Combine reference paragraphs with their corresponding cited paragraphs."""
    result: List[str] = []
    reference_map: dict[str, str] = {}  # number -> reference text
    
    # First pass: collect references
    for para in paragraphs:
        if is_reference(para):
            ref_num = get_reference_number(para)
            reference_map[ref_num] = para
        else:
            result.append(para)
    
    # Second pass: combine references with their citations
    for i, para in enumerate(result):
        cited_refs = extract_reference_numbers(para)
        if cited_refs:
            matching_refs = [reference_map[num] for num in cited_refs if num in reference_map]
            if matching_refs:
                result[i] = '\n'.join([para] + matching_refs)
    
    return result

def is_postscript(text: str) -> bool:
    """Determine if a paragraph is a postscript based on length and ending."""
    text = text.strip()
    return len(text.split()) < 20 and text.endswith('.')

def combine_postscripts(paragraphs: List[str]) -> List[str]:
    """Combine postscript paragraphs with their preceding paragraphs."""
    result: List[str] = []
    ps_buffer: List[str] = []
    
    for para in paragraphs:
        if is_postscript(para):
            ps_buffer.append(para)
        else:
            # If we have postscripts but no preceding paragraph, add them as separate paragraphs
            if ps_buffer and not result:
                result.extend(ps_buffer)
                ps_buffer.clear()
            
            if result and ps_buffer:
                # Combine all accumulated postscripts with the previous paragraph
                result[-1] = '\n'.join([result[-1]] + ps_buffer)
                ps_buffer.clear()
            result.append(para)
    
    # Handle any remaining postscripts at the end
    if ps_buffer:
        if result:
            result[-1] = '\n'.join([result[-1]] + ps_buffer)
        else:
            # If we only had postscripts, add them as separate paragraphs
            result.extend(ps_buffer)
        
    return result

def is_diagram(text: str) -> bool:
    """Determine if a paragraph is part of a diagram based on repeated dashes."""
    # Look for lines that are primarily made up of dashes (e.g., "----" or "---|---")
    lines = text.split('\n')
    for line in lines:
        stripped = line.strip()
        if stripped and (
            stripped.count('-') / len(stripped) >= 0.5  # At least 50% dashes
            or stripped.startswith('|')  # Common in ASCII diagrams
            or stripped.endswith('|')    # Common in ASCII diagrams
        ):
            return True
    return False

def combine_diagrams(paragraphs: List[str]) -> List[str]:
    """Combine diagram paragraphs with their preceding paragraphs."""
    result: List[str] = []
    diagram_buffer: List[str] = []
    
    for para in paragraphs:
        if is_diagram(para):
            diagram_buffer.append(para)
        else:
            if result and diagram_buffer:
                # Combine all accumulated diagram lines with the previous paragraph
                result[-1] = '\n'.join([result[-1]] + diagram_buffer)
                diagram_buffer.clear()
            result.append(para)
    
    # Handle any remaining diagram parts at the end
    if diagram_buffer and result:
        result[-1] = '\n'.join([result[-1]] + diagram_buffer)
        
    return result

def is_quote(text: str) -> bool:
    """Determine if a paragraph is a quote block based on quotation marks."""
    text = text.strip()
    return text.startswith('"') and text.endswith('"')

def combine_quotes(paragraphs: List[str]) -> List[str]:
    """Combine quote blocks with their preceding paragraphs."""
    result: List[str] = []
    quote_buffer: List[str] = []
    
    for para in paragraphs:
        if is_quote(para):
            quote_buffer.append(para)
        else:
            if result and quote_buffer:
                # Combine all accumulated quotes with the previous paragraph
                result[-1] = '\n'.join([result[-1]] + quote_buffer)
                quote_buffer.clear()
            result.append(para)
    
    # Handle any remaining quotes at the end
    if quote_buffer and result:
        result[-1] = '\n'.join([result[-1]] + quote_buffer)
        
    return result

def split_into_chunks(text: str, doc_id: str) -> List[Chunk]:
    """Split document text into chunks based on paragraphs"""
    # Normalize newlines and split into basic paragraphs
    normalized_text = text.replace('\r\n', '\n')
    paragraphs = [p.strip() for p in normalized_text.split('\n\n') if p.strip()]
    
    # Apply paragraph combination rules in order, from most specific to least
    processed_paragraphs = combine_references(paragraphs)  # Most specific
    processed_paragraphs = combine_diagrams(processed_paragraphs)
    processed_paragraphs = combine_quotes(processed_paragraphs)
    processed_paragraphs = combine_postscripts(processed_paragraphs)
    processed_paragraphs = combine_headers(processed_paragraphs)  # Most general
    
    return [
        Chunk(
            chunk_id=f"{doc_id}-{i}",
            doc_id=doc_id,
            text=para,
            position=i,
            metadata={}
        )
        for i, para in enumerate(processed_paragraphs)
    ]

def test_parse(doc_name: Optional[str] = None) -> None:
    """Test the text parsing functionality on input documents"""
    paths = get_paths(DATA_DIR)
    log_file = paths.logs_dir / "parse_test_results.log"
    
    # Get list of documents to process
    docs: List[Path] = []
    if doc_name:
        doc_path = paths.docs_dir / doc_name
        if not doc_path.exists():
            logger.error(f"Document not found: {doc_name}")
            return
        if doc_path.is_dir():
            # Add all documents from the folder
            docs.extend(list(doc_path.glob("*.txt")) + list(doc_path.glob("*.md")))
        else:
            docs = [doc_path]
    else:
        # Process all documents and folders
        for path in paths.docs_dir.iterdir():
            if path.is_dir():
                docs.extend(list(path.glob("*.txt")) + list(path.glob("*.md")))
            elif path.suffix.lower() in ['.txt', '.md']:
                docs.append(path)
    
    # Process each document
    with open(log_file, "w") as f:
        for doc_path in docs:
            f.write(f"\n{'='*80}\n")
            f.write(f"Processing document: {doc_path.name}")
            if doc_path.parent.name != paths.docs_dir.name:
                f.write(f" (in folder: {doc_path.parent.name})")
            f.write(f"\n{'='*80}\n\n")
            
            try:
                text = doc_path.read_text(encoding='utf-8')
                chunks = split_into_chunks(text, doc_path.stem)
                
                for i, chunk in enumerate(chunks, 1):
                    f.write(f"\nCHUNK {i}:\n")
                    f.write(f"{'-'*40}\n")
                    f.write(f"{chunk.text}\n")
                    f.write(f"{'-'*40}\n")
            
            except Exception as e:
                error_msg = f"Error processing {doc_path.name}: {str(e)}"
                logger.error(error_msg)
                f.write(f"\nERROR: {error_msg}\n")
    
    logger.info(f"Parse test results written to {log_file}")

def run_test() -> None:
    """Test the text parsing functionality with a sample document."""
    test_text = '''I. The Principles of Magic

1. The Laws of Magic

The fundamental principles of magic have been well studied. Here we shall
examine them in detail, starting with sympathetic magic, which relies on
hidden connections between objects.[1] This principle has been observed
across many cultures.[2]

A simple example of sympathetic magic can be illustrated as follows:

                   Types of Magic
                         |
            ------------------------
            |                      |
    Sympathetic Magic       Contagious Magic
    (Like affects like)    (Part affects whole)

The above classification helps us understand the basic principles that
govern magical thinking in primitive societies. Let me illustrate with a
common spell:

"By this pin I pierce the heart,
 As this wax melts and falls apart,
 So shall my enemy feel the smart."

J. G. FRAZER.

1 BRICK COURT, TEMPLE,
June 1922.

[1] See Smith, J. "Principles of Sympathetic Magic," Journal of 
Anthropology, 1899.

[2] For additional examples, see Brown, R. "Cross-Cultural Survey 
of Magical Practices," 1901.
'''

    # Process the test document
    chunks = split_into_chunks(test_text, "test_doc")
    
    # Print results
    print("\nTest Results:")
    print("=============")
    print(f"Number of chunks: {len(chunks)}")
    print("\nChunk contents:")
    for i, chunk in enumerate(chunks, 1):
        print(f"\nChunk {i}:")
        print("-" * 40)
        print(chunk.text)
        print("-" * 40)

if __name__ == "__main__":
    run_test()
