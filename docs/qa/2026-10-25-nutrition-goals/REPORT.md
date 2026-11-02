# Nutrition goal chat verification — 2026-10-25

Explicit daily calorie preferences now reach the deterministic calculator instead of being discarded. Protein remains based on recorded body weight and goal; fat and carbohydrate are recomputed for the requested calories. Calculated defaults and user preferences retain separate provenance.

Clear save/change instructions and confirmation of a pending proposal persist the target, selected local day snapshot, revision and retry receipt atomically. Other dates retain their snapshots. The frontend refreshes daily targets, remaining intake and target history after a chat save. Tentative questions remain proposals.

Validation:
- 101 tests passed across nutrition targets, nutrition chat/logging, nutrition storage and roadmap workflows.
- Frontend TypeScript and production build passed. Existing bundle-size advisory remains.
- Live connected-assistant check in a temporary fixture database passed: “I think we can go to 1800 no?” proposed 1,800; “Set my goal to 1800 calories” saved; “Change my goal to 1900 calories” saved the next revision. The fixture macros changed from 128 g protein / 50 g fat / 210 g carbohydrate to 128 g / 53 g / 228 g.
- Additional tests cover the reported transcript, shared streaming chat, direct API saves, retry deduplication, receipt-failure rollback, existing day snapshots, negation, questions, unrelated confirmations and explicit-target safeguards.

The live test did not change the user's personal target.
