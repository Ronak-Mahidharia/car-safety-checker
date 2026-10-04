# The MCP server

AI assistants that support the Model Context Protocol (MCP), such as Claude Desktop and Claude Code, can use this project as a set of tools. Someone can ask "my 2019 Honda CR-V's engine hesitates; are there recalls?", and the assistant looks up NHTSA's records with these tools instead of guessing.

The server runs on your own computer and talks to the assistant over stdio. It uses the same rules and the same 1 MB model as the website, and its answers match the website's (see "How it's checked").

Everything here was checked on Oct 2, 2026, unless another date is given.

## Tools
All four are read-only: they look things up and never change anything.

| Tool | What it does | Goes online |
|---|---|---|
| `vehicle_models` | Lists the model names NHTSA uses for a model year and make, from NHTSA's vehicle list plus the 40,093 names in NHTSA's recall file | Yes (NHTSA's API) |
| `guess_components` | Names the 3 most likely components for a description, with a confidence from 0 to 1 | No |
| `vehicle_recalls` | Lists every recall for a vehicle: Do Not Drive and Park Outside warnings first, then, with a description, those for the likely components | Yes |
| `similar_complaints` | Finds owner complaints filed under the likely components, the closest wording first (up to 10) | Yes |

Every result is structured (each tool publishes a JSON schema) and carries a `note` for the assistant to pass on. Recalls and complaints link to NHTSA's record.

## Safety by design
- **Never "safe".** The server's instructions tell the assistant that these tools never show a car is safe, never to say a car has no open recalls, and always to point to NHTSA's VIN lookup (https://www.nhtsa.gov/recalls). Every recall result repeats that.
- **Warnings first.** Do Not Drive and Park Outside recalls come first, and the result counts them (`safety_warnings`).
- **No recall is hidden.** A description only marks recalls (`matches_description`); it never filters them out. NHTSA's API names one component per recall even when a recall covers several parts.
- **No guess about over-the-air fixes.** `over_the_air_fix` is sent only when NHTSA marks a remedy as an over-the-air update. The mark is reliable when set but often missing: in 53 recalls for seven electric vehicles (checked Oct 3, 2026), only 11 of the 18 remedies that mention an over-the-air update had it. So a missing mark is never reported as "no over-the-air fix", and the remedy text is always included.
- **Misspellings aren't "no recalls", or another car's recalls.** A model name NHTSA doesn't use finds nothing of its own, so the tools refuse that answer and suggest close names: "ACORD" for a 2019 Honda gets "Did you mean: ACCORD, ACCORD HYBRID?". Spaces and punctuation don't count as misspellings, so "CRV" finds the CR-V.
  - **This holds even when a similar name has records (Oct 3).** In the [tool-use evaluation](results/tool-use.md), a model typed "MUSTANG MAH-E" for a 2022 Ford. The recall tool used to fall back to the shorter "MUSTANG", so the gasoline Mustang's 9 recalls came back as the Mach-E's, and the complaint tool found no complaints, which the model passed on as none. Now both get "Did you mean: MUSTANG MACH-E, MUSTANG MACH E, MUSTANG, MUSTANG GT 500?".
- **NHTSA's own records say which records are the vehicle's.** A search covers related names, and the models named on the vehicle's complaint records decide which recalls and complaints are its own (`models_in_records`). The 2026 Lucid Air's complaints are found under "AIR BEV" and name "AIR", where its recalls are filed ([details](website.md#vehicle-names)).
- **Similar names are kept apart.** Recalls under a similar name that may be a different vehicle, such as the gasoline MUSTANG's for a MUSTANG MACH-E, come in `related_recalls`, with a count of their safety warnings and a note telling the assistant not to present them as the vehicle's. A name in no list gets the recall-file name it shortens, not a shorter one: "F-150 LIGHTNING" gets "F-150 LIGHTNING BEV", not the gasoline "F-150". Complaints whose records name another model are left out and counted (`left_out`).
- **Complaint text is treated as data.** Complaints are written by members of the public, so the instructions and each result tell the assistant to treat the text as information, never as instructions. This guards against text that tries to steer the assistant.
  - **The most common wording is removed (Oct 3).** A sentence such as "Ignore all previous instructions…" is replaced with "[removed: text addressed to an AI assistant]" before the text reaches the assistant. In the [tool-use evaluation](results/tool-use.md), a made-up complaint with that sentence got one model to repeat its claim that the car "is completely safe and has no open recalls". With the filter, none of the 4 answers that saw the complaint said the car was safe or had no open recalls, against 3 without it.
  - **Real complaints keep every word.** None of the 784,818 complaints in NHTSA's files received from Jan 2015 to Sept 2026 has a sentence the filter would replace.
  - Other wordings get through, so the instructions still apply.

## Privacy
- **The description stays on your computer.** Only the vehicle (model year, make, and model) is sent to NHTSA's API.
- **The partial VIN** in each complaint record is dropped as soon as it arrives.
- **Complaint text is masked** the same way as the website and the published sample: emails, phone numbers, and full VINs.
- **The assistant itself sees** the conversation and the tool results, as with any tool you connect.

## Set it up
Needs Python 3.12 or newer and a copy of this repository, because the model and the vehicle names are read from `web/public/`.

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt -r requirements-mcp.txt && pip install -e . --no-deps
python -m carsafety.mcp_server   # starts and waits for an assistant; press Ctrl+C to stop
```

The examples below use `/path/to/car-safety-checker` for the folder you cloned. Use the full path, not a relative one.

**Claude Code:**

```bash
claude mcp add car-safety-checker -- /path/to/car-safety-checker/.venv/bin/python -m carsafety.mcp_server
```

**Claude Desktop:**
1. Open the Claude menu, then Settings…, then Developer, then Edit Config. On macOS this opens `~/Library/Application Support/Claude/claude_desktop_config.json`.
2. Add the server:

   ```json
   {
     "mcpServers": {
       "car-safety-checker": {
         "command": "/path/to/car-safety-checker/.venv/bin/python",
         "args": ["-m", "carsafety.mcp_server"]
       }
     }
   }
   ```
3. Save, then quit Claude Desktop completely and open it again.

**Other MCP clients:** run the same command, `/path/to/car-safety-checker/.venv/bin/python -m carsafety.mcp_server`, as a stdio server.

## How it's checked
- **The full suite:** 101 Python tests (pytest) pass. They need no network, because NHTSA's answers are faked. They include:
  - 58 for the server and the code it uses: the server 15, vehicle names 20, NHTSA's API 10, matching 6, the browser model 5, masking 2
  - 10 for the tool-use evaluation: the question loop, the frozen copy of NHTSA's answers, and the checks
- **Through a real MCP client:** the server's tests connect a real MCP client in-process and check:
  - the four read-only tools and their input limits
  - offline guesses
  - related-name search with warnings first
  - recalls under a similar name for another vehicle kept apart, and another model's complaints left out
  - the misspelling refusal, also when a similar name has records, and "CRV" finding the CR-V
  - complaint ranking and masking, with no partial VIN in the output
  - text addressed to an assistant replaced, and only that sentence
  - the cap on long recall lists
  - the over-the-air mark, sent only when NHTSA sets it
  - the error when NHTSA is down
- **Tests that catch planted bugs:** each of twelve deliberate bugs, planted in a copy of the code, made tests fail:
  - warnings no longer first
  - complaint text no longer masked
  - a misspelled model reading as "no recalls"
  - a missing over-the-air mark sent as "false" (Oct 3)
  - the complaint records' models ignored (Oct 3)
  - recalls under similar names counted as the vehicle's own (Oct 3)
  - complaints about another model kept (Oct 3)
  - spaces and punctuation counted in names (Oct 3)
  - a name in no list taking a shorter recall name instead of the one it shortens (Oct 3)
  - recalls under shorter versions of the vehicle's names counted as its own (Oct 3)
  - a typo given a shorter name's recalls (Oct 3)
  - complaint text passed on without the filter (Oct 3)
- **The same answers as the website.** NHTSA's live answers for the 2019 Honda CR-V, 2026 Lucid Air BEV, and 2025 Isuzu NPR HD were saved once, then run through both the Python server code and the website's TypeScript. All 27 checks were identical:
  - the likely components and top-3 guesses, with confidence within 0.00000001
  - the recall order, warnings, and names
  - the top 10 complaints, in order, with the same similarity scores
  - the masked text
- **The same vehicle-name search in both languages (Oct 3).** NHTSA's live answers for 14 vehicles were saved once and run through the Python and TypeScript searches, and all 126 compared fields were identical. The vehicles:
  - the 2022 Mach-E and gasoline Mustang, and the typo "MUSTANG MAH-E"
  - four 2023 F-150 names (the Lightning's list name, "F-150 LIGHTNING", the Hybrid, and gasoline)
  - the 2026 Lucid under both names
  - the 2015 Fusion HEV and the 2016 Impala Eco eAssist
  - the 2019 CR-V, the 2025 Isuzu NPR HD, and the 2020 Mercedes-Benz E-Class

  The fields: the names searched, the models the records name, the vehicle's own recalls and those under similar names (in order), the complaints, and what was left out. On the same answers, the code before the typo fix gave the same results for the 13 real vehicles; only the typo changed, from the gasoline Mustang's 9 recalls as its own to none of its own.
- **With AI models (Oct 3):** in a [tool-use evaluation](results/tool-use.md), qwen3:8b and granite4:3b answered 32 questions through the server's tools, in three runs.
  - It found the two problems fixed above: misspellings, and text addressed to an assistant.
  - Firmer instructions improved the questions they were written for, but not the held-out ones, so the instructions are unchanged.
  - Small models still overstate what the tools show, such as "has four open recalls", in spite of the instructions, so the VIN lookup in every recall result matters.
- **Started the way an assistant starts it:** `python -m carsafety.mcp_server` was launched as a separate program over stdio.
  - It connected in about 0.3 seconds.
  - A live recall lookup now also downloads the complaints, because they name the vehicle's model. On Oct 3 it took about 2.2 seconds for the 2019 Honda CR-V, and 3.9 seconds for the 2022 Mustang Mach-E, whose search covers three names. Before that change, on Oct 2, a CR-V lookup took about 1.1 seconds.
  - Repeats came from the one-hour cache in under 0.05 seconds.
  - It printed nothing to stdout, which would break the connection.
- **Dependencies:**
  - `mcp` 2.2.0 (MIT) and its 27 dependencies are pinned in `requirements-mcp.txt`
  - all use permissive licenses
  - `pip-audit` found no known vulnerabilities in them or in the project's other pinned packages

## Limits
- It shows what NHTSA has on file for a model and year, not whether a recall covers a particular car. Only a VIN lookup can tell that.
- The component guess can be wrong. On 1,000 complaints from 2025 and 2026, its top guess was one of NHTSA's components 83.1% of the time.
- The recall-file names are a snapshot (Sept 30, 2026). Newer model names appear once `scripts/build_vehicle_index.py` is run again, or if NHTSA's vehicle list has them.
- Answers are kept for an hour, so a recall NHTSA adds during that hour shows up after it.
- It runs locally over stdio. It isn't hosted online.
