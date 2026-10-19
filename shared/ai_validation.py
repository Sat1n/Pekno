"""Contracts shared by model output, storage, and semantic search."""

import math
from numbers import Real
from collections.abc import Sequence

from shared.api_errors import ApiError
from shared.error_codes import (
    ERR_AI_EMPTY_SUMMARY,
    ERR_EMBEDDING_DIMENSION_MISMATCH,
    ERR_EMBEDDING_INVALID,
)

# This is the existing pgvector schema, not a model-specific preference.
EMBEDDING_DIMENSIONS = 768
_FLOAT32_MAX = 3.4028234663852886e38


class EmbeddingValidationError(ApiError):
    def __init__(self, code: str, actual_dimension: int | None, reason: str):
        self.expected_dimension = EMBEDDING_DIMENSIONS
        self.actual_dimension = actual_dimension
        super().__init__(
            code,
            f"Invalid embedding: expected dimension {EMBEDDING_DIMENSIONS}, "
            f"actual dimension {actual_dimension}; {reason}.",
            status_code=502,
        )


def validate_embedding(vector: object) -> list[float]:
    if not isinstance(vector, Sequence) or isinstance(vector, (str, bytes, bytearray)):
        raise EmbeddingValidationError(ERR_EMBEDDING_INVALID, None, "expected a numeric vector")
    dimension = len(vector)
    if not dimension:
        raise EmbeddingValidationError(ERR_EMBEDDING_INVALID, 0, "empty vector")
    if dimension != EMBEDDING_DIMENSIONS:
        raise EmbeddingValidationError(ERR_EMBEDDING_DIMENSION_MISMATCH, dimension, "dimension mismatch")
    result = []
    for value in vector:
        if isinstance(value, bool) or not isinstance(value, Real):
            raise EmbeddingValidationError(ERR_EMBEDDING_INVALID, dimension, "non-numeric component")
        try:
            number = float(value)
        except (OverflowError, ValueError):
            raise EmbeddingValidationError(ERR_EMBEDDING_INVALID, dimension, "invalid numeric component") from None
        if not math.isfinite(number) or abs(number) > _FLOAT32_MAX:
            raise EmbeddingValidationError(ERR_EMBEDDING_INVALID, dimension, "component must be finite float32")
        result.append(number)
    return result


def validate_summary(content: object) -> str:
    if not isinstance(content, str) or not content.strip():
        raise ApiError(ERR_AI_EMPTY_SUMMARY, "The model returned an empty summary.", status_code=502)
    return content.strip()
