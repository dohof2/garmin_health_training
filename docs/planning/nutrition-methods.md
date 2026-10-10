# T9 nutrition methods and boundaries

Implemented 10 October 2026. The authoritative calculations live in `backend/app/nutrition.py`; vision is isolated in `food_vision.py`. This is a local prototype with editable estimates, not a validated dietary prescription or photo measurement system.

## Intake and sources

Manual entries accept kcal, protein, fat and carbohydrate grams for an entered portion or per 100 g. Grams, millilitres and servings are explicit; there is no guessed cups-to-grams conversion. Unknown nutrients remain null. Per-100g inputs rescale with grams; whole-portion inputs do not. Every item stores its source, raw nutrient basis/snapshot, portion basis (weighed, label serving, estimated or photo estimate), and uncertainty. Weighing a portion does not make reference nutrient values exact measurements.

Meals require a visible review and explicit confirmation. Creates have stable operation identities to prevent retry duplication; conflicting reuse of an identity is rejected. Edits check the current revision and retain old snapshots. Remove/restore is recoverable. UTC timestamps include an explicit offset; daily totals use the selected IANA timezone, including DST. The editor shows the resulting local date before confirmation and asks users to verify backdated offsets.

Daily totals sum only active local meal items. They show known subtotals and unknown-item counts separately for each nutrient. Remaining values are withheld wherever intake/target is unknown. An empty log does not prove zero intake. Garmin expenditure and imported Garmin nutrition summaries remain separate and are never added to this log.

## Free offline nutrient lookup

The chosen first-edition source is the [official USDA Foundation Foods JSON download, April 2026](https://fdc.nal.usda.gov/download-datasets/). A downloadable public reference avoids API keys, rate limits, sending food history to a service, and runtime internet dependency. The [USDA API guide](https://fdc.nal.usda.gov/api-guide/) describes the alternative keyed API. No U9 key is needed for this implementation. Broader packaged/regional coverage uses manual label entries and recipes; adding SR Legacy/FNDDS/branded catalogs can be a later extension.

The bundled normalized cache contains 363 nonempty Foundation records (the source has 32 empty records), 311 with all four supported nutrients. Ten negative source carbohydrate values are represented as unknown with an explicit warning rather than being clamped to zero. Values are per 100 g edible food. Energy uses specific Atwater (2048), then general Atwater (2047), then reported kcal (1008); grams use protein 1003, total fat 1004 and carbohydrate 1005. The extraction validates units. Food names include cooking state; the user selects the match instead of automatically substituting a similar food.

`backend/app/resources/usda-foundation.json` records release, official URL and archive SHA-256. Reproduce it from the official ZIP with:

```sh
PYTHONPATH=backend .venv/bin/python -m app.usda_foods /path/to/FoodData_Central_foundation_food_json_2026-04-30.zip
```

The builder reads bounded JSON without extracting archive paths. Normalized reference data is public; user food logs remain in the ignored local database. Logged meals keep their nutrient snapshot even if a later catalog changes.

## Recipes and reusable meals

Save the entire ingredient list and total serving yield. Reusing N servings multiplies each ingredient's amount and stored nutrients by N / yield. Unknowns propagate. Cooking water changes do not imply raw/cooked mass equality; serving fractions control scaling. Recipe edits retain immutable revisions. Saving a recipe does not log intake; using it loads a separate editable meal draft and retains the source recipe revision.

## Local photo review

PNG/JPEG inputs are limited to 6 MiB, 8192 pixels per side and 20 megapixels. Only local Ollama receives the photo; the selected local model must support vision. [Ollama's chat API](https://docs.ollama.com/api/chat) supports image messages and JSON-schema outputs. The request disables thinking, uses bounded generation and a 90-second timeout. There is no paid/provider fallback, no model tool access, and no automatic write or nutrient calculation from model text. Malformed, overlong or invalid responses fail with manual logging still available.

Vision proposes names, unvalidated gram ranges and questions about preparation, oils and scale. Counts/ranges may be wrong or refer to one item rather than the entire plate. The user confirms which foods were eaten, edits total edible grams, and selects USDA matches or enters label values. Database matching preserves edited grams and photo uncertainty. The final nutrient totals are calculated deterministically and reviewed before saving. Original photo bytes are held only for the page/request, not written to disk, SQLite, exports or backups. Model uncertainty text is data, never an instruction.

The public USDA apple image smoke test verifies food identification and the complete correction/match/save flow. It does not validate multi-food identification, hidden ingredients, serving mass or calorie accuracy. Known-portion meal trials during use remain useful; no automatic accuracy claim is made.

## Reviewed targets

Manual targets accept calories, optional macros, and an optional distinct training-day calorie override. An alternative adult maintenance preview uses the [Mifflin–St Jeor equation](https://pubmed.ncbi.nlm.nih.gov/2305711/): resting kcal = 10 × kg + 6.25 × cm − 5 × age + 5 (male coefficient) or −161 (female coefficient). The user explicitly chooses the coefficient and supplies inputs; identity is not inferred. The resting estimate is multiplied by the user's chosen usual activity factor, which includes exercise. The equation estimates resting expenditure; the multiplier is an explicit planning assumption rather than a measured energy requirement. The application does not automatically propose a weight-loss deficit, surplus or macro prescription.

Example fixture: age 30, 80 kg, 180 cm, male coefficient produces 1780 resting kcal; an explicitly chosen 1.5 multiplier gives 2670 kcal. Adult age/size/multiplier bounds are input-validation defaults, not evidence of suitability for every individual. Clinical/special-population targets and trend-based calibration require separate review and are not automated here.

Garmin workout calories are never added to the activity-factor result. A saved training-day calorie value replaces the day's calories; it is not an exercise addition. Training days use accepted local plans in the selected timezone, excluding skipped/cancelled sessions. Without a manual override, training/rest calories are identical. Macros are explicitly entered, optional and unchanged between day types; inconsistent macro-derived energy produces a review warning.

Target versions are append-only with stale-revision checks and explicit effective dates. The target used at the first meal save for a day/timezone is frozen; later target/plan edits do not rewrite it. A day logged before any target exists has no frozen target until a later meal save can capture one. Historical overrides do not replace already captured day snapshots. Target history and day snapshots travel with JSON and full backups.
