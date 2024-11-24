from text_parser import split_into_chunks


def test_text_parsing() -> None:
    """Test the text parsing functionality with a sample document."""
    # Test input
    test_text = '''I. The Principles of Magic\u0000\u001F

1. The Laws of Magic

The fundamental principles of magic have been well studied. Here we shall
examine them in detail, starting with sympathetic magic, which relies on
hidden connections between objects.[1] This principle has been observed
across many cultures.[2]

    The Law of Similarity states that like produces like. This means that
    an effect resembles its cause. For example, a yellow flower might be
    used to treat jaundice, or a heart-shaped leaf for heart problems.

    The Law of Contagion states that things which have once been in contact
    continue to act on each other at a distance. This explains why personal
    belongings are often used in spells targeting specific individuals.

        • Sub-principles of Contagion:
          • Once connected, always connected
          • Part equals whole
          • Essence persists through time

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

    # Process the document
    chunks = split_into_chunks(test_text, "test_doc")
    
    # Expected output for each chunk
    expected_chunks = [
        '''I. The Principles of MagicC
1. The Laws of Magic
The fundamental principles of magic have been well studied. Here we shall
examine them in detail, starting with sympathetic magic, which relies on
hidden connections between objects.[1] This principle has been observed
across many cultures.[2]
[1] See Smith, J. "Principles of Sympathetic Magic," Journal of 
Anthropology, 1899.
[2] For additional examples, see Brown, R. "Cross-Cultural Survey 
of Magical Practices," 1901.


    The Law of Similarity states that like produces like. This means that
    an effect resembles its cause. For example, a yellow flower might be
    used to treat jaundice, or a heart-shaped leaf for heart problems.

    The Law of Contagion states that things which have once been in contact
    continue to act on each other at a distance. This explains why personal
    belongings are often used in spells targeting specific individuals.

        • Sub-principles of Contagion:
          • Once connected, always connected
          • Part equals whole
          • Essence persists through time''',
        
        '''A simple example of sympathetic magic can be illustrated as follows:
                   Types of Magic
                         |
            ------------------------
            |                      |
    Sympathetic Magic       Contagious Magic
    (Like affects like)    (Part affects whole)''',
        
        '''The above classification helps us understand the basic principles that
govern magical thinking in primitive societies. Let me illustrate with a
common spell:
"By this pin I pierce the heart,
 As this wax melts and falls apart,
 So shall my enemy feel the smart."
J. G. FRAZER.
1 BRICK COURT, TEMPLE,
June 1922.'''
    ]

    # Assert the number of chunks matches
    if len(chunks) != len(expected_chunks):
        raise AssertionError(f"Expected {len(expected_chunks)} chunks, got {len(chunks)}")

    # Assert each chunk's text matches exactly
    for i, (chunk, expected) in enumerate(zip(chunks, expected_chunks)):
        if chunk.text.strip() != expected.strip():
            raise AssertionError(
                f"Chunk {i+1} does not match expected output.\n"
                f"Expected:\n{expected.strip()}\n"
                f"Got:\n{chunk.text.strip()}"
            )
