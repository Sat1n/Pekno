from pydantic import BaseModel, HttpUrl
from typing import List, Union, Dict, Literal

class HoverBlockBase(BaseModel):
    block_type: str

class KVBlock(HoverBlockBase):
    block_type: Literal["kv"] = "kv"
    kv_data: Dict[str, Union[str, int, float, bool]]
    # Example: {"stars": 100, "forks": 20}

class QuoteBlock(HoverBlockBase):
    block_type: Literal["quote"] = "quote"
    author: str
    avatar_url: str
    content: str
    date: str | None = None

class MarkdownBlock(HoverBlockBase):
    block_type: Literal["markdown"] = "markdown"
    text: str

class ProgressItem(BaseModel):
    label: str
    value: float
    color: str | None = None

class ProgressBlock(HoverBlockBase):
    block_type: Literal["progress"] = "progress"
    items: List[ProgressItem]

# The response from the Hover API will be a list of these polymorphic blocks.
HoverResponse = List[Union[KVBlock, QuoteBlock, MarkdownBlock, ProgressBlock]]
