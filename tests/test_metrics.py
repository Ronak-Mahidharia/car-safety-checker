import pytest

from carsafety.metrics import score


def test_perfect_predictions_score_one():
    truth = [{"AIR BAGS"}, {"ENGINE", "POWER TRAIN"}]
    result = score(truth, truth)
    assert result["micro_f1"] == 1.0
    assert result["macro_f1"] == 1.0
    assert result["exact_match"] == 1.0


def test_counts_hits_misses_and_extras():
    # complaint 1: right. complaint 2: one label right, one missed, one extra.
    truth = [{"AIR BAGS"}, {"ENGINE", "POWER TRAIN"}]
    predicted = [{"AIR BAGS"}, {"ENGINE", "STEERING"}]
    result = score(truth, predicted)
    # pooled: 2 true positives, 1 false positive, 1 false negative
    assert result["micro_precision"] == pytest.approx(2 / 3)
    assert result["micro_recall"] == pytest.approx(2 / 3)
    assert result["micro_f1"] == pytest.approx(2 / 3)
    assert result["exact_match"] == 0.5
    by_label = {s.label: s for s in result["per_label"]}
    assert by_label["POWER TRAIN"].recall == 0.0
    assert by_label["STEERING"].support == 0  # predicted but never true


def test_macro_f1_ignores_labels_that_are_never_true():
    truth = [{"AIR BAGS"}, {"ENGINE"}]
    predicted = [{"AIR BAGS"}, {"ENGINE", "STEERING"}]
    result = score(truth, predicted)
    # AIR BAGS f1 = 1, ENGINE f1 = 1; STEERING has no true cases, so it's left out of the average
    assert result["macro_f1"] == 1.0
    assert result["micro_precision"] == pytest.approx(2 / 3)


def test_empty_prediction_is_all_misses():
    result = score([{"TIRES"}], [set()])
    assert result["micro_recall"] == 0.0
    assert result["micro_f1"] == 0.0


def test_mismatched_lengths_raise():
    with pytest.raises(ValueError):
        score([{"TIRES"}], [])
