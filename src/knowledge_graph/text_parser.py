import re
from typing import List, Optional
from custom_dataclasses import Chunk
from pathlib import Path
from shared_resources import DATA_DIR, logger, DEBUG_ENABLED
from utils import get_paths
import unicodedata


def sanitize_text(text: str) -> str:
    """Clean text by removing invalid/non-printable characters while preserving indentation."""
    # Process the text line by line to preserve indentation
    lines = text.split('\n')
    cleaned_lines = []
    
    for line in lines:
        # Preserve leading whitespace
        leading_space = len(line) - len(line.lstrip())
        line_content = line[leading_space:]
        
        # Clean the content part
        cleaned_content = ''.join(
            char for char in line_content 
            if unicodedata.category(char)[0] != "C" or char in '\n\t'
        )
        cleaned_content = unicodedata.normalize('NFKC', cleaned_content)
        
        # Restore the exact same number of leading spaces
        cleaned_lines.append(' ' * leading_space + cleaned_content)
    
    # Rejoin lines and preserve paragraph breaks
    return '\n'.join(cleaned_lines)

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
            # Use a list comprehension that preserves the order of citations as they appear
            matching_refs = []
            for num in sorted(cited_refs, key=lambda x: para.find(f'[{x}]')):
                if num in reference_map:
                    matching_refs.append(reference_map[num])
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

def get_indentation_level(text: str) -> int:
    """Get indentation level of first non-empty line in text.
    Returns number of spaces/characters of indentation."""
    for line in text.split('\n'):
        if line.strip():  # First non-empty line
            # Count leading spaces and common indent markers
            indent = len(line) - len(line.lstrip(' \t>-*•'))
            return indent
    return 0

def combine_indented_paragraphs(paragraphs: List[str]) -> List[str]:
    """Combine paragraphs that share the same indentation level."""
    result: List[str] = []
    current_text: List[str] = []
    current_words = 0
    MAX_WORDS = 1000
    
    def flush_current() -> None:
        """Helper to flush current_text to result."""
        if current_text:
            result.append('\n\n'.join(current_text))
            current_text.clear()
            nonlocal current_words
            current_words = 0
    
    for para in paragraphs:
        para_words = len(para.split())
        
        # Start new chunk if this paragraph alone exceeds limit
        if para_words > MAX_WORDS:
            flush_current()
            result.append(para)
            continue
            
        # Get indentation levels
        current_level = get_indentation_level(current_text[-1]) if current_text else 0
        new_level = get_indentation_level(para)
        
        # Combine if either:
        # 1. This is first indented paragraph after its parent (new_level > current_level)
        # 2. This continues a sequence of same-level indented paragraphs (both must be > 0)
        # 3. Won't exceed word limit
        if (current_text and 
            ((new_level > current_level) or (new_level == current_level and new_level > 0)) and 
            current_words + para_words <= MAX_WORDS):
            current_text.append(para)
            current_words += para_words
        else:
            flush_current()
            current_text.append(para)
            current_words = para_words
    
    flush_current()  # Handle any remaining paragraphs
    return result

def enforce_max_chunk_size(paragraphs: List[str], max_words: int = 1500) -> List[str]:
    """Split any chunks that exceed max_words as a last resort."""
    result: List[str] = []
    
    for para in paragraphs:
        words = para.split()
        
        # If paragraph is within limit, keep as is
        if len(words) <= max_words:
            result.append(para)
            continue
            
        # Otherwise split into chunks of max_words
        current_pos = 0
        while current_pos < len(words):
            # Get next chunk of words
            chunk_words = words[current_pos:current_pos + max_words]
            
            # Create chunk text
            chunk_text = ' '.join(chunk_words)
            
            # Add ellipsis at start if not first chunk
            if current_pos > 0:
                chunk_text = '...' + chunk_text
                
            # Add ellipsis at end if not last chunk
            if current_pos + max_words < len(words):
                chunk_text = chunk_text + '...'
                
            result.append(chunk_text)
            current_pos += max_words
            
    return result

def split_into_chunks(text: str, doc_id: str) -> List[Chunk]:
    """Split document text into chunks based on paragraphs"""
    # Sanitize text
    text = sanitize_text(text)
    
    # Normalize newlines and split into basic paragraphs
    normalized_text = text.replace('\r\n', '\n')
    paragraphs = [p for p in normalized_text.split('\n\n') if p.strip()]
    
    # Apply paragraph combination rules in order
    processed_paragraphs = combine_references(paragraphs)
    processed_paragraphs = combine_diagrams(processed_paragraphs)
    processed_paragraphs = combine_quotes(processed_paragraphs)
    processed_paragraphs = combine_postscripts(processed_paragraphs)
    processed_paragraphs = combine_indented_paragraphs(processed_paragraphs)
    processed_paragraphs = combine_headers(processed_paragraphs)
    
    # Final safety check for maximum chunk size
    processed_paragraphs = enforce_max_chunk_size(processed_paragraphs)
    
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
            # Recursively add all documents from the folder and subfolders
            docs.extend(list(doc_path.rglob("*.txt")) + list(doc_path.rglob("*.md")))
        else:
            docs = [doc_path]
    else:
        # Recursively process all documents in all folders
        docs.extend(list(paths.docs_dir.rglob("*.txt")) + list(paths.docs_dir.rglob("*.md")))
    
    # Process each document
    with open(log_file, "w") as f:
        for doc_path in docs:
            f.write(f"\n{'='*80}\n")
            f.write(f"Processing document: {doc_path.name}")
            if doc_path.parent != paths.docs_dir:
                # Show full relative path for nested documents
                relative_path = doc_path.parent.relative_to(paths.docs_dir)
                f.write(f" (in folder: {relative_path})")
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
                if DEBUG_ENABLED:
                    raise
    
    logger.info(f"Parse test results written to {log_file}")
