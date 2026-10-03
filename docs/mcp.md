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
- **Misspellings aren't "no recalls".** A model name NHTSA doesn't use finds nothing, so the tools refuse that answer and suggest close names. For example, "CRV" for a 2019 Honda gets "Did you mean: CR-V, HR-V, CIVIC?"
- **Related names are searched.** The 2026 Lucid Air's recalls are filed under "AIR" and its complaints under "AIR BEV", so a search for either name covers both ([details](website.md#vehicle-names)).
- **Complaint text is treated as data.** Complaints are written by members of the public, so the instructions and each result tell the assistant to treat the text as information, never as instructions. This guards against text that tries to steer the assistant.

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
- **The full suite:** 70 Python tests (pytest) pass, including 32 for the server and the code it uses. They need no network, because NHTSA's answers are faked.
- **Through a real MCP client:** the server's tests connect a real MCP client in-process and check:
  - the four read-only tools and their input limits
  - offline guesses
  - related-name search with warnings first
  - the misspelling refusal
  - complaint ranking and masking, with no partial VIN in the output
  - the cap on long recall lists
  - the over-the-air mark, sent only when NHTSA sets it
  - the error when NHTSA is down
- **Tests that catch planted bugs:** each of four deliberate bugs, planted in a copy of the code, made tests fail:
  - warnings no longer first
  - complaint text no longer masked
  - a misspelled model reading as "no recalls"
  - a missing over-the-air mark sent as "false" (Oct 3)
- **The same answers as the website.** NHTSA's live answers for the 2019 Honda CR-V, 2026 Lucid Air BEV, and 2025 Isuzu NPR HD were saved once, then run through both the Python server code and the website's TypeScript. All 27 checks were identical:
  - the likely components and top-3 guesses, with confidence within 0.00000001
  - the recall order, warnings, and names
  - the top 10 complaints, in order, with the same similarity scores
  - the masked text
- **Started the way an assistant starts it:** `python -m carsafety.mcp_server` was launched as a separate program over stdio.
  - It connected in about 0.3 seconds and answered a live recall lookup in about 1.1 seconds.
  - A repeat of the same lookup came from the one-hour cache in about 0.001 seconds.
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
