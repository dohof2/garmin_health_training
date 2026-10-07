# Phase 0 Feasibility Report

Date: 19 September 2026; Garmin archive evidence updated 6 October 2026
Status: Initial assessment completed and real Garmin archive validated. Garmin login, workout publication, and GitHub publication have not been performed.

## Outcome

The planned local application is feasible on this computer. The machine has enough storage and memory for the application stack, SQLite data, historical imports, charts, and a small local model. The largest remaining risks are the real Garmin archive schemas, live Garmin Connect behavior, and representative Ollama inference outside the Codex sandbox.

Phase 0 does not authorize Phase 1 automatically. It records evidence and makes unresolved dependencies visible.

## T1.1 — Computer and runtime baseline

| Item | Observed result | Assessment |
|---|---|---|
| Computer | MacBook Air (13-inch, M5), model Mac17,3 | Suitable for the local application |
| Architecture | Apple silicon (`arm64`) | Use native arm64/universal installers |
| Memory | 16 GiB unified memory | Suitable for the app and modest quantized models; avoid assuming large models can coexist with heavy desktop workloads |
| Storage | 512 GB physical storage; about 302 GiB available after model downloads | Ample for source data, database, backups, and selected models |
| Operating system | macOS 27.0, build 26A428 | Meets Ollama's macOS 14+ requirement |
| Developer tools | Apple Command Line Tools and Apple clang 21.0.0 | Suitable for native dependency builds when required |
| SQLite | 3.54.0 | Suitable for the planned local database |
| Git | Apple Git 2.54.0 | Suitable |
| Python | Python.org Python 3.13.15 at `/usr/local/bin/python3.13`; `python3` resolves to the same version | Verified arm64/universal installation; virtual-environment creation, pip 26.2.1, OpenSSL 3.0.21, and SQLite 3.50.4 work |
| Node.js/npm | Node.js 24.21.0 LTS and npm 11.19.0 at `/usr/local/bin` | Verified arm64/universal installation and ready for the React/TypeScript foundation |
| Ollama | Official app bundle 0.34.2 in `/Applications/Ollama.app`; CLI not on shell PATH | Installed and code-signature verification passed |

### Installation-source rule

Future runtime installers must come from their official sources: Python from [python.org](https://www.python.org/downloads/macos/), Node.js from [nodejs.org](https://nodejs.org/en/download), and Ollama from [ollama.com](https://ollama.com/download/mac). Project libraries should be pinned and obtained from their projects' documented official registries. No Homebrew or third-party installer is required.

Installed runtime baseline: Python 3.13.15 from Python.org and Node.js 24.21.0 LTS from nodejs.org. Their downloaded packages matched the publishers' SHA-256 values and were signed by the Python Software Foundation and Node.js Foundation respectively. Installation and post-installation runtime checks completed on 21 September 2026.

## T1.2 — Garmin archive inspection

Status: complete on 6 October 2026.

The original 200,606,293-byte Garmin ZIP is stored in the ignored local data
directory. Its CRC test passed, all 285 JSON files parsed successfully, and the
outer and eight nested archives contain no traversal paths or symbolic links.
The export includes 1,054 unique summarized activities (30 January 2012 through
29 September 2026 UTC), 3,050 daily summaries, 2,908 sleep records, and 55,448
nested FIT files, plus GPX, TCX, training metrics, routes, workouts, gear, and
other account data. The original file was not extracted or modified.

Detailed privacy-safe evidence, counts, date coverage, checksum, and importer
implications are recorded in [`garmin-export-inventory.md`](garmin-export-inventory.md).

## T1.3 — Garmin Connect coverage assessment

The official Garmin Connect Developer Program cannot be assumed for this personal application: Garmin states that the program is for business use. [Garmin program FAQ](https://developer.garmin.com/gc-developer-program/program-faq/)

The current prototype candidate remains the unofficial, MIT-licensed `python-garminconnect` project. Its current documentation exposes health, activity, historical, workout, scheduling, and related account methods, but the library uses Garmin web services and is not an official Garmin API. [Project repository](https://github.com/cyberjunky/python-garminconnect)

Documented candidate coverage includes:

- Daily health/activity summaries and calorie data.
- Heart rate, sleep, stress, HRV, SpO2, body composition, and other advanced metrics.
- Activities, activity details, zones, trends, and historical range queries.
- Token caching, renewal behavior, and MFA support.
- Workout upload, update, delete, schedule, unschedule, and device push operations.

Limitations:

- Documentation establishes candidate methods, not what this Garmin account actually exposes.
- Endpoints may change without notice because the integration is unofficial.
- Not all data types necessarily support efficient range or updated-since queries.
- Account-specific fields, empty responses, correction detection, rate limits, and deletion semantics require read-only live testing.
- Full data-type/date coverage remains a T1.4/U2 validation item.

## T1.4 — Live Garmin login and read-only query

Status: intentionally not performed. This requires U2.

The first live test must use the application's local sign-in flow. The user enters credentials and MFA privately; credentials or codes must never be sent through chat or stored in Git. Begin with a small read-only query and record authentication, token renewal, retry, rate-limit, and returned-field behavior.

## T1.5 — Local model feasibility

### Installed and downloaded

- Ollama app 0.34.2 was already installed by the user.
- Its app bundle passed `codesign --verify --deep --strict`.
- `qwen3.5:4b` was downloaded from Ollama's official registry: 3.4 GB, manifest ID `2a654d98e6fb`.
- `qwen3.5:2b` was downloaded from Ollama's official registry: 2.7 GB.
- Ollama verified the downloaded model digests before writing their manifests.
- The resulting local Ollama directory occupies about 5.7 GB.

### Test result and limitation

Both models reached model initialization, but inference could not run inside the Codex sandbox. The temporary server could see 16 GiB system memory, but macOS did not expose a usable Metal command queue to the sandboxed process. Both model sizes failed on a tiny Metal buffer allocation, indicating an execution-environment restriction rather than a meaningful model-size comparison.

The temporary benchmark server was stopped. Nothing is listening on port 11434, so no Ollama background server was left running by this assessment.

Required follow-up: launch Ollama normally outside the Codex sandbox and run the same bounded text, structured-output, tool-selection, and vision tests. Record model load time, first-token latency, generation rate, peak memory pressure, answer accuracy, and whether another model is needed. Start with `qwen3.5:2b`; test 4B only if memory pressure remains acceptable.

Do not treat either model as selected for production until this follow-up succeeds. Deterministic application code—not the model—must continue to perform health calculations and validated writes.

## T1.6 — Workout support inspection

No workout was created, scheduled, or published.

Current `python-garminconnect` documentation provides typed workout models for running, cycling, strength, swimming, walking, hiking, multisport, and fitness equipment. It also documents upload, scheduling, read-back, in-place update, unscheduling, deletion, and device-push methods. Strength support includes a bundled exercise catalog. [Workout examples](https://github.com/cyberjunky/python-garminconnect#typed-workouts-pydantic-models)

This is enough to justify building preview and mapping prototypes, but not to claim compatibility. Each supported sport must still pass the planned deliberate publish/read-back/device test. Known risks include unsupported step types, exercise-name mismatches, differences between calendar presence and device delivery, and partial create/schedule success.

## T1.7 — Feasibility decision

Proceeding to the local foundation is reasonable. Phase 1 work can start with synthetic fixtures and no account connection.

Open validation gates:

1. **U2:** Test Garmin authentication and small read-only queries.
2. **Local AI:** Run the Ollama benchmark in a normal user session outside the Codex sandbox.

The U1 archive gate is complete. The remaining gates block claims about live
account coverage and usable local-model performance. They do not block real
archive importer implementation, database design, dashboards, maintenance
storage, or provider-neutral AI interfaces.
