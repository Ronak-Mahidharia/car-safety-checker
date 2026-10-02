"""The plain-Python browser model must match scikit-learn exactly. Data here is made up."""
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression

from carsafety.browser_model import BrowserModel, terms

DOCS = [
    "The ENGINE stalled on the highway",
    "engine light came on and the engine stalled again",
    "Brakes failed at the stop sign",
    "brake pedal went to the floor",
    "café naïve brakés squeal",  # accents, which scikit-learn strips
    "a b c",  # one-letter words only, so no terms at all
]
ENGINE = [1, 1, 0, 0, 0, 1]


def fitted():
    vectorizer = TfidfVectorizer(ngram_range=(1, 2), sublinear_tf=True, strip_accents="unicode")
    model = LogisticRegression(solver="liblinear").fit(vectorizer.fit_transform(DOCS), ENGINE)
    vocabulary = [None] * len(vectorizer.vocabulary_)
    for term, i in vectorizer.vocabulary_.items():
        vocabulary[i] = term
    return vectorizer, model, vocabulary


def test_terms_match_scikit_learns_analyzer():
    vectorizer, _, _ = fitted()
    analyzer = vectorizer.build_analyzer()
    for doc in DOCS + ["It's the 2019's model, ok?", "TOYOTA RAV4 hybrid's battery died", "Naïve CAFÉ"]:
        assert terms(doc) == analyzer(doc)


def test_probabilities_match_scikit_learn():
    vectorizer, model, vocabulary = fitted()
    ours = BrowserModel(["ENGINE"], vocabulary, vectorizer.idf_, model.coef_, model.intercept_, threshold=0.5)
    for doc in DOCS + ["only unknown words here zzz qqq"]:
        expected = model.predict_proba(vectorizer.transform([doc]))[0, 1]
        assert abs(ours.probabilities(doc)[0] - expected) < 1e-9


def test_predict_always_returns_at_least_one_label():
    vectorizer, model, vocabulary = fitted()
    ours = BrowserModel(["ENGINE"], vocabulary, vectorizer.idf_, model.coef_, model.intercept_, threshold=0.99)
    assert ours.predict("the brakes failed") == {"ENGINE"}  # nothing reaches 0.99, so the most likely one
