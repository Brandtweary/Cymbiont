from typing import List, Optional
from custom_dataclasses import Chunk, Triple
from shared_resources import openai_client, logger, DEBUG
from utils import log_performance
from prompts import safe_format_prompt, NER_PROMPT, TRIPLE_PROMPT
import json
from json.decoder import JSONDecodeError

NER_OPENAI_MODEL = "gpt-4o-mini"

