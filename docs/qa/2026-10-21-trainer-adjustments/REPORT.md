# Casual trainer adjustment QC

50/50 requests passed: 26 reviewable changes, 13 reasoned declines, 11 focused clarifications.

Each request ran through `chat_stream`, including an existing coaching context. The isolated fixture has consistent cycling history and an easy-only week so the positive intensity branch can be tested. Proposal cases were actually saved in disposable copies. Previews made no workout changes. Separate regression tests cover poor recorded sleep, existing quality sessions, recovery weeks, stale revisions and forged proposals.

These are deterministic chat/tool tests, not 50 remote-model generations. The test fixture is invented; the personal plan was not changed. Saving a weekly change adapts materialized sessions in the next seven days, while retaining the program goal and blocks. Requests to increase volume require a reviewed replacement week; strength load changes require exercise details; schedule moves require a clear source and destination.

Repeat: `.venv/bin/python scripts/run_training_adjustment_qc.py`

| # | Request | Expected and observed |
|---|---|---|
| 1 | I am feeling good give me harder workout | proposal |
| 2 | Feeling fresh, make my ride tougher today | proposal |
| 3 | Can we do tempo today? | proposal |
| 4 | Give me some intervals today | proposal |
| 5 | I feel great, increase the intensity today | proposal |
| 6 | Can you give me a harder workuot today please | proposal |
| 7 | Make today easier please | proposal |
| 8 | My legs are tired, cut today back | proposal |
| 9 | Can we back off this week? | proposal |
| 10 | Reduce my cycling this week by 20% | proposal |
| 11 | Cut this week by 50% | proposal |
| 12 | I need a lighter week | proposal |
| 13 | Make all rides easy this week | proposal |
| 14 | Halve the training this week | proposal |
| 15 | I only have 30 minutes today | proposal |
| 16 | Only got 20 mins for my ride today | proposal |
| 17 | I can only ride for 45 minutes today | proposal |
| 18 | Make the long ride easier on Friday | proposal |
| 19 | Skip my ride today | proposal |
| 20 | I need a rest day today | proposal |
| 21 | Cancel cycling this week | proposal |
| 22 | I have knee pain, make the ride easy | proposal |
| 23 | I feel sick, skip today | proposal |
| 24 | I have a fever, should I rest today? | proposal |
| 25 | I am sore, make it easier | proposal |
| 26 | My sleep was terrible, give me a harder workout | not_recommended |
| 27 | I slept 3 hours but want a harder ride | not_recommended |
| 28 | I have knee pain but give me harder intervals | not_recommended |
| 29 | I am sick but want sprints | not_recommended |
| 30 | I am exhausted but make it harder | not_recommended |
| 31 | Make every workout harder this week | not_recommended |
| 32 | Double my cycling this week | not_recommended |
| 33 | Increase cycling time this week by 20% | not_recommended |
| 34 | Make Friday a longer ride | not_recommended |
| 35 | Add more time to my weekly training | not_recommended |
| 36 | Give me sprint training today | not_recommended |
| 37 | Can we do anaerobic intervals today? | not_recommended |
| 38 | Give me spritns today | not_recommended |
| 39 | Make tomorrow easier | needs_input |
| 40 | Make next week lighter | needs_input |
| 41 | I only have 5 minutes today | needs_input |
| 42 | Make today 200 minutes | needs_input |
| 43 | Reduce this week by 150% | needs_input |
| 44 | Move my ride to tomorrow | needs_input |
| 45 | Swap Monday and Wednesday training | needs_input |
| 46 | I feel good | needs_input |
| 47 | Make my strength workout harder | needs_input |
| 48 | My last ride felt too hard | needs_input |
| 49 | Don't make today harder | needs_input |
| 50 | Can you make today easir? | proposal |
