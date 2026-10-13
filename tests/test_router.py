import numpy as np

from carsafety.router import best_confidence, best_threshold, labels_from, route

CLASSES = ["AIR BAGS", "ENGINE", "STEERING"]


def test_components_at_or_above_the_threshold_or_else_the_most_likely_one():
    probs = np.array([[0.7, 0.3, 0.1], [0.2, 0.25, 0.1], [0.5, 0.5, 0.0]])
    assert labels_from(probs, CLASSES, 0.3) == [{"AIR BAGS", "ENGINE"}, {"ENGINE"}, {"AIR BAGS", "ENGINE"}]


def test_the_best_threshold_has_the_highest_micro_f1_and_the_lower_one_wins_a_tie():
    truth = [["AIR BAGS"], ["ENGINE"]]
    probs = np.array([[0.9, 0.4, 0.0], [0.1, 0.9, 0.0]])
    best, f1 = best_threshold(truth, probs, CLASSES, thresholds=(0.3, 0.5, 0.6))
    assert best == 0.5 and f1[0.5] == f1[0.6] == 1.0 and f1[0.3] < 1.0


def test_the_router_keeps_the_keyword_models_answer_only_where_its_sure():
    keyword_probs = np.array([[0.95, 0.05, 0.0], [0.4, 0.35, 0.25]])
    labels, sent = route(keyword_probs, [{"AIR BAGS"}, {"AIR BAGS"}], [{"ENGINE"}, {"STEERING"}], confidence=0.9)
    assert labels == [{"AIR BAGS"}, {"STEERING"}] and sent.tolist() == [False, True]


def test_the_best_confidence_sends_fewer_complaints_on_when_two_are_equal():
    keyword_probs = np.array([[0.95, 0.05, 0.0], [0.55, 0.45, 0.0], [0.65, 0.35, 0.0]])
    truth = [["AIR BAGS"], ["ENGINE"], ["AIR BAGS"]]
    keyword_labels = [{"AIR BAGS"}, {"AIR BAGS"}, {"AIR BAGS"}]
    tuned_labels = [{"ENGINE"}, {"ENGINE"}, {"AIR BAGS"}]
    best, tried = best_confidence(truth, keyword_probs, keyword_labels, tuned_labels, confidences=(0.6, 0.7, 0.96))
    # 0.6 sends only the second complaint, and 0.7 the third too, which gets the same answer: all right either way
    assert tried[0.6]["micro_f1"] == tried[0.7]["micro_f1"] == 1.0 and tried[0.96]["micro_f1"] < 1.0
    assert best == 0.6 and tried[0.6]["sent"] < tried[0.7]["sent"]
