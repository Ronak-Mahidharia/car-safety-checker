# The website

Live at [ronak-mahidharia.github.io/car-safety-checker](https://ronak-mahidharia.github.io/car-safety-checker/), published with GitHub Pages after every merge to `main` ([workflow](../.github/workflows/pages.yml)).

Numbers measured on NHTSA's live data are from Oct 2–3, 2026. NHTSA adds records over time, so they can change.

## What it does
1. You choose the model year, make, and model.
2. The page asks NHTSA's public API for that vehicle's recalls and owner complaints, under every name NHTSA uses for it ([vehicle names](#vehicle-names)).
3. You describe the problem. The keyword model, running in your browser, names the likely components ([browser model](results/browser-model.md)).
4. The page shows:
   - **Every recall for the vehicle.** Recalls with a Do Not Drive or Park Outside advisory come first, then recalls for the likely components, then the rest, newest first in each group.
   - **Recalls under similar names**, listed apart, when NHTSA files recalls under a name that may be a different vehicle.
   - **The 10 complaints closest to your wording**, from those NHTSA filed under the likely components.
   - **A link to NHTSA's own page** for each recall and complaint (`https://www.nhtsa.gov/recalls?nhtsaId=…`), which shows the record and offers it as a PDF.

It never says a car is safe, and it always points to NHTSA's official VIN lookup.

**Also on the page:**
- **Start over** clears the vehicle, the description, and the results, and removes the vehicle from the address.
- **Dark mode:** a switch in the header picks light or dark. Until it's used, the page follows the device's setting.

## What NHTSA's API does, and how the page handles it

| What the API does | How the page handles it |
|---|---|
| Plain GET requests work from any website (it echoes the site's origin), but the OPTIONS pre-check for other requests answers 501 | Requests send no custom headers |
| A vehicle with no records comes back as HTTP 400 with an empty list | Treated as "no records" |
| Recall dates are day/month/year, while complaint dates are month/day/year. Recall 19V865000's "05/12/2019" is Dec 5, 2019 in NHTSA's recall file | Read separately, and tested against dates in the recall file |
| `parkIt` is the Do Not Drive advisory and `parkOutSide` is Park Outside (checked against recalls 26V517000 and 26V540000 in the recall file) | Shown as badges and listed first |
| `overTheAirUpdate` marks a remedy as an over-the-air update. It's reliable when set but often missing: in 53 recalls for seven electric vehicles, only 11 of the 18 remedies that mention an over-the-air update had it | The "Over-the-air fix" label appears only when the mark is set, and every recall shows NHTSA's remedy text under "Fix" |
| A recall lists one component, even when the recall file lists several. Recall 20V771000 has 6 for the 2019 Honda Accord; the API shows 1 | Every recall is shown, not just the matching ones |
| Each complaint record includes a partial VIN | Dropped as soon as the data arrives, and never kept or shown |
| A complaint's components are joined by a comma with no space; names that contain a comma have a space after it ("FUEL SYSTEM, GASOLINE") | Split by that rule. None of NHTSA's 53 category names breaks it |
| The complaint search takes the names in NHTSA's vehicle list, while recalls are filed under the names in its recall file, and each complaint record names the model the recall way. The vehicle list also leaves out some recall names (next section) | The picker also offers the recall file's names. A search covers related names, and the model each complaint record names decides which records are the vehicle's own |
| A complaint search can return another model's complaints too (next section) | They're left out, and the page says how many |
| Searches ignore capitals | Names are kept in capitals |

## Vehicle names
NHTSA's API names the same vehicle in more than one way:
- **Complaints and recalls are filed under different names.** The complaint search takes the names in NHTSA's vehicle list, the recall search takes the names in its recall file, and each complaint record names the model the recall way. The 2026 Lucid Air's complaints are found under "AIR BEV", and every one of their records says "AIR", the name its recalls are filed under. The vehicle list offers only "AIR BEV", so picking it alone once showed no recalls, including a Park Outside one.
- **Spelling differs.** The 2022 Ford Mustang Mach-E's complaints are found under "MUSTANG MACH-E", and its 9 recalls are filed under "MUSTANG MACH E".
- **A search can return another model's records.** NHTSA's search for the 2023 "F-150 (SUPER CREW) LIGHTNING BEV" returns 203 complaints, and 94 of their records name the F-150 HYBRID.
- **Some names are missing from the list.** For 2025 Isuzu, the list offers no models at all, while the recall file has 9, including the NPR HD with a Do Not Drive recall.

**How a search works.**
1. **Related names are searched too:** names spelled the same apart from spaces and punctuation ("MUSTANG MACH-E" and "MUSTANG MACH E", "CRV" and "CR-V"), and names that are the chosen one with more words, in order and starting with the same word ("F-150" and "F-150 (SUPER CREW) GAS"). "MODEL 3" and "MODEL Y" stay separate.
2. **NHTSA's own records say which vehicle it is.** The complaints found under the chosen name name its model: "AIR" for "AIR BEV". Models spelled like the chosen name or within it count first, because a search can return another model's records. If none is, models the chosen name is within count. If there's still none, the records are trusted: the 2023 "F-150 (SUPER CREW) HEV" records name the F-150 HYBRID.
3. **The vehicle's recalls** are those filed under the chosen name, a name spelled the same, and the models its records name (in every spelling they use). The closest recall-file names count too, judged in this order:
   - a name spelled the same
   - the one name that is the vehicle's name with more words: "F-150 LIGHTNING BEV" for "F-150 LIGHTNING", a name in no list and with no complaints. If several names fit, none is picked.
   - the most specific names within it: "F-150 LIGHTNING BEV", not "F-150", for the Lightning's list name. This needs a name NHTSA lists or one its records name. For a typo such as "MUSTANG MAH-E", which is in no list and has no records, the shorter "MUSTANG" would be a guess: the gasoline Mustang's recalls stay under similar names. The picker clears a model from a link that NHTSA doesn't list, so this matters most for [the MCP server](mcp.md), where an assistant types the name.
4. **Recalls under other related names are listed apart,** under "Recalls under similar names", and never dropped, because a name can't tell whether a recall applies: one filed only under "ESCAPE" may also cover an "ESCAPE PHEV". So are recalls under shorter versions of the vehicle's recall names (two words or more), which NHTSA's API sometimes uses instead. A safety warning among them is pointed out at the top of the results.
5. **Complaints count** when their record names the vehicle's model, or a version of it with more words that the chosen name's own search returned (the 2015 "FUSION HEV" search returns FUSION HYBRID complaints). The rest are left out, and the page says how many.

The page says which names were searched, and which model NHTSA's records name when it differs from the chosen one. Each record filed under another name is marked.

**Why NHTSA's own records decide.** A simpler rule links two names only when one is the other plus more words. [`check_vehicle_names.py`](../scripts/check_vehicle_names.py) measured it against this search on NHTSA's live API. The script picked 30 model years and makes in proportion to their complaints, then up to 8 names from NHTSA's vehicle list for each: 216 names with complaints, covering 49,257 complaints. The simpler rule:
- **counted recalls filed only under another model's name** as the vehicle's own for 16 names (7.4%, or 6.6% of the complaints). The 2022 Jeep Grand Cherokee got 11 recalls filed only under GRAND CHEROKEE 4XE, the plug-in hybrid.
- **missed recalls filed under the vehicle's own names** for 25 names (11.6%, or 13.1% of the complaints). The 2020 Mercedes-Benz E-Class's records name models such as E 450, and the 15 recalls filed under them were missed. The BMW 3 Series missed 11 filed under 330I. Ford's F-250 and F-350 records name F-250 and F-350, while their recalls are filed under F-250 SD and F-350 SD; the 2019 F-250 Crew Cab missed 16. One of them is the 2016 IMPALA ECO EASSIST, whose records name the MALIBU (see Limits).
- **did one or the other** for 41 names (19.0%, or 19.7% of the complaints).

NHTSA's search for 8 of the names (3.7%) also returned complaints about another model, 343 in all, which this search leaves out. For example, the 2022 GRAND CHEROKEE L search returned 148 GRAND CHEROKEE 4XE complaints. Every recall that NHTSA's recall file lists under the sampled vehicles' own names was found. NHTSA's downloadable files name complaints the way recalls are filed, so this mismatch shows only in the live API.

**What the picker lists.**
- **Two sources:** it combines NHTSA's vehicle-list API with the 40,093 model names in NHTSA's recall file (model years 1983 to 2027). Either source is enough if the other can't be reached.
- **Small downloads:** the recall-file names take 0.57 MB, one small file per model year, and only the chosen year's file is loaded.

The recall-file names are a snapshot of `FLAT_RCL_POST_2010.txt` (SHA-256 `558c17887cba06880eb72dde84b67d1fcab85f5e0ddf28699be1c1cb4ef49cf5`, downloaded Sept 30, 2026). Run the script again to refresh them.

## Privacy
- **Your description:** analyzed in the browser, and it's never sent anywhere. Only the year, make, and model go to NHTSA.
- **Complaint text:** masked the same way as the published test sample. Emails, phone numbers, and full VINs are hidden.
- **No tracking:** no cookies, no analytics, and no fonts or scripts from other servers. The page remembers one thing: a light or dark choice, kept in the browser's storage and never sent anywhere.
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
**83 tests (Vitest), run in CI:**
- The browser model gives the same labels as the Python model on all 1,000 test complaints.
- Component names get the same label as in [`labels.py`](../src/carsafety/labels.py) for all 800 names in NHTSA's files, and lists of components split the same way (158 cases).
- Masking matches [`privacy.py`](../src/carsafety/privacy.py) (19 cases), and it leaves the 1,000 already-checked sample complaints unchanged.
- API answers are handled correctly:
  - requests are plain GETs
  - a 400 reply counts as empty
  - both date orders are read correctly
  - advisories are read
  - the partial VIN is dropped
  - each complaint record's model is read, and records found under several names are sorted into the vehicle's own and those under similar names
- Recall order, complaint matching, related names, the address rules, and the rendered page each have tests, including that the Safety warnings tile appears only when there's a warning.
- Vehicle names: the TypeScript gives the Python code's answers for every case in [`names.json`](../web/src/lib/fixtures/names.json): 1,047 names, 448 name pairs, and the recall-name and model cases. Searches are tested on the Mach-E and Mustang, the F-150 Lightning and Hybrid, the Fusion, Mercedes-Benz spellings, and the Lucid. Six deliberate bugs, introduced in a copy of the name code, each made tests fail. On NHTSA's saved live answers for 14 vehicles, one of them a typo, the TypeScript and Python searches agreed on all 126 compared fields ([details](mcp.md#how-its-checked)).

**On the built site in headless Chrome:**
- Click-through checks on a 1,280 px screen and a 390 px phone all pass:
  - the first Tab reaches "Skip to results"
  - "Show full details" opens the whole card
  - an example fills in only the description
  - "Find matches" updates the guesses
  - a phone scrolls to the results
  - the address keeps only the vehicle
- The 2019 Honda CR-V, the 2026 Lucid Air BEV, and the 2025 Isuzu NPR HD all load, with advisories first.
- The 2022 Mustang Mach-E and Mustang, and the 2023 F-150 (SUPER CREW) LIGHTNING BEV, load with their own recalls counted and those under similar names listed apart. The Lightning's list leaves out 94 F-150 HYBRID complaints and says so, and lists the two recalls filed only under "F-150 LIGHTNING" under similar names.
- None of the 315 partial VINs in the CR-V's 1,101 complaint records appears on the page.
- There are no JavaScript errors and no policy violations. The only console messages are the browser noting NHTSA's expected 400 replies for names with no records.
- Nothing is wider than the screen at 390 px, in light and dark mode.
- Every text color pair meets WCAG AA contrast, and most meet AAA. The dark mode switch's outline, track, and thumb stand out at least 3:1 in both themes (lowest 3.23:1).
- **Dark mode, Start over, and the record links, on desktop and phone:**
  - the switch follows the device until it's used, works over both device settings, and saves the choice without cookies
  - after a reload, the saved choice applies before the page's own code runs, so the other theme never flashes
  - the switch has a name and a state for screen readers
  - Start over clears the vehicle, the description, the results, and the address, then moves focus to the first field
  - every "NHTSA record" link opens NHTSA's page for that record, in a new tab

## Limits
- It shows what NHTSA has on file for a model and year, not whether a recall covers your car. Only a VIN lookup can tell that.
- The component guess can be wrong (see Accuracy). Recalls are never hidden because of it.
- The recall-file names are a snapshot. New model names appear in the picker once the script is run again, and until then only if NHTSA's vehicle-list API has them.
- NHTSA's API files a few recalls under names that are in neither its vehicle list nor its recall file. Two 2023 F-150 Lightning recalls, 23V168000 and 23V688000, are found only under "F-150 LIGHTNING". The page finds them by searching shorter versions of the vehicle's recall names, but lists them under similar names, because the shorter name alone can't show they apply. A name like that which isn't a shorter version of one the page knows can't be found; NHTSA's VIN lookup can.
- When NHTSA's records for a name point to a different vehicle, the page follows them and says so. NHTSA's search for the 2016 "IMPALA ECO EASSIST" returns only complaints whose records name the MALIBU.
- Whether a recall filed only under a similar name covers a vehicle can't be told from the name, so those recalls are listed apart, not counted or hidden.

## Run it
Needs Node.js 24.

```bash
cd web && npm ci
npm run dev                          # http://localhost:5173
npm run build && npx vite preview    # the built site, with its security policy
```

To rebuild the data files, run `python scripts/build_vehicle_index.py` and `python scripts/build_web_fixtures.py`. Both need the files from `scripts/download_data.py`.
