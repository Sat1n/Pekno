from hub.core.search import SearchService


def test_cosine_distance_to_relevance_clamps_to_unit_interval():
    assert SearchService._cosine_distance_to_relevance(0.0) == 1.0
    assert SearchService._cosine_distance_to_relevance(0.25) == 0.75
    assert SearchService._cosine_distance_to_relevance(1.0) == 0.0
    assert SearchService._cosine_distance_to_relevance(1.5) == 0.0
    assert SearchService._cosine_distance_to_relevance(-0.1) == 1.0


def test_keyword_rank_to_relevance_stays_readable_for_keyword_only_hits():
    assert SearchService._keyword_rank_to_relevance(1) == 1.0
    assert SearchService._keyword_rank_to_relevance(2) == 0.97
    assert SearchService._keyword_rank_to_relevance(100) == 0.0
