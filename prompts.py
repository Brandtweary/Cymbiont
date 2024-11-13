NER_PROMPT = '''Extract named entities (nouns and noun phrases) from the text. Format as JSON list.

Example:
Text: "UC Berkeley researchers collaborated with Lawrence Berkeley Lab on quantum computing."
Entities: ["UC Berkeley", "Lawrence Berkeley Lab", "quantum computing"]

Text: """
{text}
"""'''

TRIPLE_PROMPT = '''Generate RDF triples through OpenIE, using the provided named entities. Each triple should contain at least one named entity. Format as JSON list of [subject, relationship, object].

Example:
Text: "UC Berkeley researchers collaborated with Lawrence Berkeley Lab on quantum computing."
Entities: ["UC Berkeley", "Lawrence Berkeley Lab", "quantum computing"]
Triples: [
   ["UC Berkeley", "collaborated with", "Lawrence Berkeley Lab"],
   ["UC Berkeley", "researches", "quantum computing"],
   ["Lawrence Berkeley Lab", "researches", "quantum computing"]
]

Text: """
{text}
"""
Entities: {entities}'''