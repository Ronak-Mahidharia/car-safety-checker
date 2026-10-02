"""Tests for blending the keyword model with similar-complaint voting. All numbers are made up."""
import numpy as np
import pytest

from carsafety.combine import blend, top_suggestions, vote_shares

CLASSES = ["AIR BAGS", "ENGINE", "STEERING"]


def test_vote_shares_split_each_complaints_similarity_across_labels():
    labels = [[["ENGINE"], ["ENGINE", "STEERING"], ["AIR BAGS"]]]
    shares = vote_shares(labels, np.array([[0.5, 0.3, 0.2]]), CLASSES)
    assert shares[0].tolist() == pytest.approx([0.2, 0.8, 0.3])


def test_blend_weighs_the_two_sources_and_always_picks_one():
    keyword = np.array([[0.1, 0.9, 0.1], [0.3, 0.3, 0.3]])
    shares = np.array([[0.0, 0.2, 1.0], [0.1, 0.1, 0.1]])
    # complaint 1 at weight 0.5: AIR BAGS 0.05, ENGINE 0.55, STEERING 0.55 (none sits exactly on 0.5)
    assert blend(keyword, shares, CLASSES, weight=0.5, threshold=0.5) == [{"ENGINE", "STEERING"}, {"AIR BAGS"}]
    assert blend(keyword, shares, CLASSES, weight=1.0, threshold=0.5)[0] == {"ENGINE"}  # keyword model only


def test_top_suggestions_are_the_most_likely_labels_first():
    keyword = np.array([[0.12, 0.81, 0.43]])
    assert top_suggestions(keyword, CLASSES, n=2) == [[("ENGINE", 0.81), ("STEERING", 0.43)]]
