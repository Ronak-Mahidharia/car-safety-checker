# The website

Everything here was checked on Oct 2, 2026, unless another date is given.

## What it does
1. You choose the model year, make, and model.
2. The page asks NHTSA's public API for that vehicle's recalls and owner complaints.
3. You describe the problem. The keyword model, running in your browser, names the likely components ([browser model](results/browser-model.md)).
4. The page shows:
   - **Every recall for the vehicle.** Recalls with a Do Not Drive or Park Outside advisory come first, then recalls for the likely components, then the rest, newest first in each group.
   - **The 10 complaints closest to your wording**, from those NHTSA filed under the likely components.
   - **A link to NHTSA's record** for each recall and complaint.

It never says a car is safe, and it always points to NHTSA's official VIN lookup.

## What NHTSA's API does, and how the page handles it

| What the API does | How the page handles it |
|---|---|
| Plain GET requests work from any website (it echoes the site's origin), but the OPTIONS pre-check for other requests answers 501 | Requests send no custom headers |
| A vehicle with no records comes back as HTTP 400 with an empty list | Treated as "no records" |
| Recall dates are day/month/year, while complaint dates are month/day/year. Recall 19V865000's "05/12/2019" is Dec 5, 2019 in NHTSA's recall file | Read separately, and tested against dates in the recall file |
| `parkIt` is the Do Not Drive advisory and `parkOutSide` is Park Outside (checked against recalls 26V517000 and 26V540000 in the recall file) | Shown as badges and listed first |
| `overTheAirUpdate` marks a remedy as an over-the-air update. It's reliable when set but often missing: in 53 recalls for seven electric vehicles (checked Oct 3, 2026), only 11 of the 18 remedies that mention an over-the-air update had it | The "Over-the-air fix" label appears only when the mark is set, and every recall shows NHTSA's remedy text under "Fix" |
| A recall lists one component, even when the recall file lists several. Recall 20V771000 has 6 for the 2019 Honda Accord; the API shows 1 | Every recall is shown, not just the matching ones |
| Each complaint record includes a partial VIN | Dropped as soon as the data arrives, and never kept or shown |
| A complaint's components are joined by a comma with no space; names that contain a comma have a space after it ("FUEL SYSTEM, GASOLINE") | Split by that rule. None of NHTSA's 53 category names breaks it |
| Recall and complaint records often name the same vehicle differently, and the vehicle-list API misses some recall names (next section) | The picker also offers the recall file's names, and a search covers related names |
| Searches ignore capitals | Names are kept in capitals |

## Vehicle names
- **Lucid example:** the 2026 Lucid Air's recalls are filed under "AIR" and its complaints under "AIR BEV", and NHTSA's vehicle-list API offers only "AIR BEV". Picking "AIR BEV" alone would have shown no recalls, including a Park Outside one.
- **Isuzu example:** for 2025 Isuzu, the list offers no models at all, while the recall file has 9, including the NPR HD with a Do Not Drive recall.

**How often the names differ.** Measured on NHTSA's files with [`build_vehicle_index.py`](../scripts/build_vehicle_index.py): for model years 2015 to 2026, there are 12,348 recall listings for a make and year that also has complaints. Of these:
- **50.4%** use a model name that also appears in the complaints.
- **7.0%** differ only by extra words, like AIR and AIR BEV. A search covers these.
- **42.6%** match no complaint name. Most are vehicles with no complaints at all, such as trucks, buses, and RVs.

**What the picker lists.**
- **Two sources:** it combines NHTSA's vehicle-list API with the 40,093 model names in NHTSA's recall file (model years 1983 to 2027). Either source is enough if the other can't be reached.
- **Small downloads:** the recall-file names take 0.57 MB, one small file per model year, and only the chosen year's file is loaded.
- **Related names:** one name counts as related to another when it's the same name plus more words ("F-150" and "F-150 SUPERCREW"), so "MODEL 3" and "MODEL Y" stay separate. The page says when it searched more than one name, and marks each record that was filed under another name.

The recall-file names are a snapshot of `FLAT_RCL_POST_2010.txt` (SHA-256 `558c17887cba06880eb72dde84b67d1fcab85f5e0ddf28699be1c1cb4ef49cf5`, downloaded Sept 30, 2026). Run the script again to refresh them.

## Privacy
- **Your description:** analyzed in the browser, and it's never sent anywhere. Only the year, make, and model go to NHTSA.
- **Complaint text:** masked the same way as the published test sample. Emails, phone numbers, and full VINs are hidden.
- **No tracking:** no cookies, no analytics, and no fonts or scripts from other servers.
- **Content Security Policy:** the built page carries one that allows connections only to the site itself and to api.nhtsa.gov.
- **Links:** a link can fill in the form, for example `#year=2019&make=HONDA&model=CR-V&q=...`. The part after "#" never reaches the web server, and the page removes the description from the address once it has read it.

## Accuracy
The component guess comes from the browser model. On the fixed 1,000-complaint test sample:
- 0.720 micro F1
- 56.0% exact match
- its top guess was one of NHTSA's components for 83.1% of complaints

The page shows these as guesses with a confidence, never as findings.

## Design and accessibility
- **Layout:** two columns on screens 1,024 px and wider, with the search form beside the results; it stays in view while you scroll when the screen is tall enough to show all of it. Tablets and phones get one column, and on phones a search scrolls down to the results.
- **Accessible:**
  - a "Skip to results" link
  - labeled fields and visible focus
  - a status line that screen readers announce when results change
  - touch targets of 44 px or more
  - 16 px text in fields, so phones don't zoom in
  - no animation for people who turn motion off
- **Contrast:** every text color pair meets WCAG AA in both themes (lowest 6.19:1 in light and 7.00:1 in dark, against the 4.5:1 minimum), and field borders reach at least 3:1.
- **Responsible design:**
  - red is used only for NHTSA's safety warnings and harm owners reported, and nothing is green, so no part of the page reads as "safe"
  - the Safety warnings tile appears only when there's a warning, and first; a "0" there could be misread
  - example descriptions fill in only the text box, never a vehicle, so they don't suggest that any car has those problems
- **Light:** no outside fonts, icon libraries, or images. The icons are drawn for the site in SVG.

## How it's checked
**53 tests (Vitest), run in CI:**
- The browser model gives the same labels as the Python model on all 1,000 test complaints.
- Component names get the same label as in [`labels.py`](../src/carsafety/labels.py) for all 800 names in NHTSA's files, and lists of components split the same way (158 cases).
- Masking matches [`privacy.py`](../src/carsafety/privacy.py) (19 cases), and it leaves the 1,000 already-checked sample complaints unchanged.
- API answers are handled correctly:
  - requests are plain GETs
  - a 400 reply counts as empty
  - both date orders are read correctly
  - advisories are read
  - the partial VIN is dropped
  - records found under several names are merged
- Recall order, complaint matching, related names, the address rules, and the rendered page each have tests, including that the Safety warnings tile appears only when there's a warning.

**On the built site in headless Chrome:**
- Click-through checks on a 1,280 px screen and a 390 px phone all pass:
  - the first Tab reaches "Skip to results"
  - "Show full details" opens the whole card
  - an example fills in only the description
  - "Find matches" updates the guesses
  - a phone scrolls to the results
  - the address keeps only the vehicle
- The 2019 Honda CR-V, the 2026 Lucid Air BEV, and the 2025 Isuzu NPR HD all load, with advisories first.
- None of the 315 partial VINs in the CR-V's 1,101 complaint records appears on the page.
- There are no JavaScript errors and no policy violations. The only console messages are the browser noting NHTSA's expected 400 replies for names with no records.
- Nothing is wider than the screen at 390 px, in light and dark mode.
- Every text color pair meets WCAG AA contrast, and most meet AAA.

## Limits
- It shows what NHTSA has on file for a model and year, not whether a recall covers your car. Only a VIN lookup can tell that.
- The component guess can be wrong (see Accuracy). Recalls are never hidden because of it.
- The recall-file names are a snapshot. New model names appear in the picker once the script is run again, and until then only if NHTSA's vehicle-list API has them.
- Related names follow a simple rule, so names written differently, such as "F150" and "F-150", aren't linked.

## Run it
Needs Node.js 24.

```bash
cd web && npm ci
npm run dev                          # http://localhost:5173
npm run build && npx vite preview    # the built site, with its security policy
```

To rebuild the data files, run `python scripts/build_vehicle_index.py` and `python scripts/build_web_fixtures.py`. Both need the files from `scripts/download_data.py`.
