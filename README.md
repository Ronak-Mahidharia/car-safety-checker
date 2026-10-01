# Car Safety Checker

Describe a problem with your car and see the official NHTSA recalls and the owner complaints that match it, with every source linked. Its accuracy is measured against NHTSA's own labels and published here.

> **Status:** week 1 of 4. The answer key and the baselines are done; the AI comes next.

Not affiliated with or endorsed by NHTSA or the U.S. Department of Transportation. This is not a safety inspection. To check your car for open recalls, use NHTSA's official lookup at https://www.nhtsa.gov/recalls.

## The idea
When something goes wrong with a car, owners want to know two things: is this a known problem, and is there a recall? NHTSA publishes every safety complaint it receives and every recall, but searching them by hand is slow. This project takes a plain-English description, works out which part of the car it's about, and shows the matching recalls and complaints, with links to the official records.

## How accuracy is measured
Every NHTSA complaint is labeled with the components it concerns, such as ENGINE or AIR BAGS. That gives a large, official answer key:
- **Data:** 723,204 vehicle complaints received from Jan 1, 2015 to Sept 28, 2026, with 31 component labels ([answer key](docs/answer-key.md)). NHTSA renamed some categories over the years, so old names are merged into current ones ([`labels.py`](src/carsafety/labels.py)).
- **Split by date, like real use:** train on complaints received before 2024, tune on 2024, and test on 2025 to 2026. The test is always on complaints the system hasn't seen.
- **Metrics:** a complaint can have several labels, so predictions are scored with precision, recall, and F1. Micro F1 pools every label decision; macro F1 averages over labels, so rare components count as much as common ones.

## Results so far: the baselines the AI has to beat
| Baseline | Micro F1 | Macro F1 | Exact match |
|---|---|---|---|
| Most common label | 0.245 | 0.015 | 17.0% |
| Keyword model (TF-IDF + logistic regression) | 0.719 | 0.438 | 54.8% |

Scored on the full test split: 122,100 complaints received from 2025 onward. Details, including the fixed 1,000-complaint sample and per-label scores: [baseline results](docs/results/baselines.md).

## Reproduce
Requires Python 3.12 or newer.

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt && pip install -e . --no-deps
python scripts/download_data.py      # about 210 MB from NHTSA
python scripts/build_answer_key.py   # about 15 seconds
python scripts/run_baselines.py      # about 1 minute
python -m pytest
```

## Data and privacy
- **Source:** public complaint files published by NHTSA at static.nhtsa.gov. The exact files and their SHA-256 checksums are in the [answer key](docs/answer-key.md).
- **Never read:** the personal fields in those files (the owner's city, state, and partial VIN, the dealer's details, the vehicle operator's name, and the incident state).
- **Descriptions** are NHTSA's published text. In the committed test sample ([`test_sample.jsonl`](data/sample/test_sample.jsonl)), emails, phone numbers, and full VINs are also masked, and a test checks that on every change.
- **Downloaded files stay out of git:** `data/raw/` and `data/processed/` are ignored.

## Roadmap
1. **Week 1:** answer key and baselines (done)
2. **Week 2:** the AI. Identify components from a description, find similar complaints, match recalls, and score it against the baselines.
3. **Week 3:** the website, an MCP server for AI assistants, and a free live demo
4. **Week 4:** write-up, demo, and polish

## License
Code: MIT (see [LICENSE](LICENSE)). Data: public records published by NHTSA.
