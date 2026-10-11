# Assistant question bank

134 cases. Date expectations are fixed to 11 October 2026. Ordinary comparisons must use general records; GPS or similar-ride matching requires an explicit matching request.

| ID | Question | Expected behavior |
|---|---|---|
| default-comparison-01 | How was my last ride compared to other rides this year? | compare_latest_ride; ['2026-01-01', '2026-10-11'] |
| default-comparison-02 | how was my last ride compared to the rides in the last year? | compare_latest_ride; ['2025-10-11', '2026-10-11'] |
| default-comparison-03 | Compare my latest ride with other rides this month. | compare_latest_ride; ['2026-10-01', '2026-10-11'] |
| default-comparison-04 | How does my most recent bike ride stack up against rides in the past 12 months? | compare_latest_ride; ['2025-10-11', '2026-10-11'] |
| default-comparison-05 | Compare my last cycling ride to other rides last year. | compare_latest_ride; ['2025-01-01', '2025-12-31'] |
| default-comparison-06 | How was my latest ride versus other rides this week? | compare_latest_ride; ['2026-10-05', '2026-10-11'] |
| default-comparison-07 | Compare my most recent ride with other rides over the past three months. | compare_latest_ride; ['2026-07-11', '2026-10-11'] |
| clarification-01 | Compare my latest bicycle ride to other rides. | Which period |
| ride-01 | How was my last ride compared to all other rides this year? | compare_latest_ride; ['2026-01-01', '2026-10-11'] |
| ride-02 | Compare my latest bike ride with general records this year? | compare_latest_ride; ['2026-01-01', '2026-10-11'] |
| ride-03 | How does my most recent ride stack up against all rides this year? | compare_latest_ride; ['2026-01-01', '2026-10-11'] |
| ride-04 | How was my last ride compared to all other rides the last year? | compare_latest_ride; ['2025-10-11', '2026-10-11'] |
| ride-05 | Compare my latest bike ride with general records the last year? | compare_latest_ride; ['2025-10-11', '2026-10-11'] |
| ride-06 | How does my most recent ride stack up against all rides the last year? | compare_latest_ride; ['2025-10-11', '2026-10-11'] |
| ride-07 | How was my last ride compared to all other rides last year? | compare_latest_ride; ['2025-01-01', '2025-12-31'] |
| ride-08 | Compare my latest bike ride with general records last year? | compare_latest_ride; ['2025-01-01', '2025-12-31'] |
| ride-09 | How does my most recent ride stack up against all rides last year? | compare_latest_ride; ['2025-01-01', '2025-12-31'] |
| ride-10 | How was my last ride compared to all other rides this month? | compare_latest_ride; ['2026-10-01', '2026-10-11'] |
| ride-11 | Compare my latest bike ride with general records this month? | compare_latest_ride; ['2026-10-01', '2026-10-11'] |
| ride-12 | How does my most recent ride stack up against all rides this month? | compare_latest_ride; ['2026-10-01', '2026-10-11'] |
| ride-13 | How was my last ride compared to all other rides the past three months? | compare_latest_ride; ['2026-07-11', '2026-10-11'] |
| ride-14 | Compare my latest bike ride with general records the past three months? | compare_latest_ride; ['2026-07-11', '2026-10-11'] |
| ride-15 | How does my most recent ride stack up against all rides the past three months? | compare_latest_ride; ['2026-07-11', '2026-10-11'] |
| ride-16 | How was my last ride compared to all other rides last month? | compare_latest_ride; ['2026-09-01', '2026-09-30'] |
| ride-17 | Compare my latest bike ride with general records last month? | compare_latest_ride; ['2026-09-01', '2026-09-30'] |
| ride-18 | How does my most recent ride stack up against all rides last month? | compare_latest_ride; ['2026-09-01', '2026-09-30'] |
| plot-01 | Plot my weight over this year. | create_plots; ['2026-01-01', '2026-10-11'] |
| plot-02 | Plot my weight over the last year. | create_plots; ['2025-10-11', '2026-10-11'] |
| plot-03 | Plot my resting heart rate over this year. | create_plots; ['2026-01-01', '2026-10-11'] |
| plot-04 | Plot my resting heart rate over the last year. | create_plots; ['2025-10-11', '2026-10-11'] |
| plot-05 | Plot my steps over this year. | create_plots; ['2026-01-01', '2026-10-11'] |
| plot-06 | Plot my steps over the last year. | create_plots; ['2025-10-11', '2026-10-11'] |
| plot-07 | Plot my sleep score over this year. | create_plots; ['2026-01-01', '2026-10-11'] |
| plot-08 | Plot my sleep score over the last year. | create_plots; ['2025-10-11', '2026-10-11'] |
| plot-09 | Plot my sleep duration over this year. | create_plots; ['2026-01-01', '2026-10-11'] |
| plot-10 | Plot my sleep duration over the last year. | create_plots; ['2025-10-11', '2026-10-11'] |
| plot-11 | Plot my hydration over this year. | create_plots; ['2026-01-01', '2026-10-11'] |
| plot-12 | Plot my hydration over the last year. | create_plots; ['2025-10-11', '2026-10-11'] |
| plot-13 | Plot my acute training load over this year. | create_plots; ['2026-01-01', '2026-10-11'] |
| plot-14 | Plot my acute training load over the last year. | create_plots; ['2025-10-11', '2026-10-11'] |
| plot-15 | Plot my cycling cadence over this year. | create_plots; ['2026-01-01', '2026-10-11'] |
| plot-16 | Plot my cycling cadence over the last year. | create_plots; ['2025-10-11', '2026-10-11'] |
| plot-17 | Plot my cycling power over this year. | create_plots; ['2026-01-01', '2026-10-11'] |
| plot-18 | Plot my cycling power over the last year. | create_plots; ['2025-10-11', '2026-10-11'] |
| plot-19 | Plot my cycling VO2 max over this year. | create_plots; ['2026-01-01', '2026-10-11'] |
| plot-20 | Plot my cycling VO2 max over the last year. | create_plots; ['2025-10-11', '2026-10-11'] |
| plot-21 | Plot weekly median weight this year. | create_plots |
| plot-22 | Plot steps as a monthly sum this year. | create_plots |
| plot-23 | Plot daily mean resting heart rate this month. | create_plots |
| plot-24 | Plot weight with a 7-day rolling average this year. | create_plots |
| plot-25 | Plot hydration with a 14-day moving average this month. | create_plots |
| plot-26 | Plot steps as a bar chart this month. | create_plots |
| plot-27 | Plot cycling power versus speed across all rides this year. | create_plots |
| plot-28 | Plot resting heart rate versus cycling VO2 max this year with correlation. | create_plots |
| plot-29 | Plot sleep duration against cycling power on the same date this year. | create_plots |
| plot-30 | Plot body battery latest versus sleep score this month. | create_plots |
| plot-31 | Plot weight versus date this year. | create_plots |
| plot-32 | Plot cadence against sleep score on the same date this month. | create_plots |
| summary-01 | Summarize my steps over the last seven days? | get_health_summary; ['2026-10-05', '2026-10-11'] |
| summary-02 | What was my average steps over the last seven days? | get_health_summary; ['2026-10-05', '2026-10-11'] |
| summary-03 | Summarize my sleep duration over the last seven days? | get_health_summary; ['2026-10-05', '2026-10-11'] |
| summary-04 | What was my average sleep duration over the last seven days? | get_health_summary; ['2026-10-05', '2026-10-11'] |
| summary-05 | Summarize my weight over the last seven days? | get_health_summary; ['2026-10-05', '2026-10-11'] |
| summary-06 | What was my average weight over the last seven days? | get_health_summary; ['2026-10-05', '2026-10-11'] |
| summary-07 | Summarize my resting heart rate over the last seven days? | get_health_summary; ['2026-10-05', '2026-10-11'] |
| summary-08 | What was my average resting heart rate over the last seven days? | get_health_summary; ['2026-10-05', '2026-10-11'] |
| summary-09 | Summarize my sleep score over the last seven days? | get_health_summary; ['2026-10-05', '2026-10-11'] |
| summary-10 | What was my average sleep score over the last seven days? | get_health_summary; ['2026-10-05', '2026-10-11'] |
| summary-11 | Summarize my hydration over the last seven days? | get_health_summary; ['2026-10-05', '2026-10-11'] |
| summary-12 | What was my average hydration over the last seven days? | get_health_summary; ['2026-10-05', '2026-10-11'] |
| summary-13 | How many steps did I record yesterday? | get_health_summary; ['2026-10-10', '2026-10-10'] |
| summary-14 | How was my sleep this week? | get_health_summary; ['2026-10-05', '2026-10-11'] |
| summary-15 | What was my average weight last month? | get_health_summary; ['2026-09-01', '2026-09-30'] |
| summary-16 | Summarize my hydration this year. | get_health_summary; ['2026-01-01', '2026-10-11'] |
| followup-01 | All rides | compare_latest_ride; follow-up to: How was my last ride compared to other rides this year?; ['2026-01-01', '2026-10-11'] |
| followup-02 | General records | compare_latest_ride; follow-up to: How was my last ride compared to other rides this year?; ['2026-01-01', '2026-10-11'] |
| followup-03 | all rides please | compare_latest_ride; follow-up to: How was my last ride compared to other rides this year?; ['2026-01-01', '2026-10-11'] |
| followup-04 | the general comparison please | compare_latest_ride; follow-up to: How was my last ride compared to other rides this year?; ['2026-01-01', '2026-10-11'] |
| followup-05 | overall | compare_latest_ride; follow-up to: How was my last ride compared to other rides this year?; ['2026-01-01', '2026-10-11'] |
| followup-06 | All rides this year | compare_latest_ride; follow-up to: How was my last ride compared to other rides this year?; ['2026-01-01', '2026-10-11'] |
| followup-07 | Same route | find_same_course_rides; follow-up to: How was my last ride compared to other rides this year?; ['2026-01-01', '2026-10-11'] |
| followup-08 | GPS | find_same_course_rides; follow-up to: How was my last ride compared to other rides this year?; ['2026-01-01', '2026-10-11'] |
| followup-09 | only rides on the same GPS route | find_same_course_rides; follow-up to: How was my last ride compared to other rides this year?; ['2026-01-01', '2026-10-11'] |
| followup-10 | matching routes please | find_same_course_rides; follow-up to: How was my last ride compared to other rides this year?; ['2026-01-01', '2026-10-11'] |
| default-comparison-08 | Compare my latest ride with other rides this year without GPS. | compare_latest_ride; ['2026-01-01', '2026-10-11'] |
| followup-11 | Add a trend line and correlation | create_plots; follow-up to: Plot weight over the last year. |
| followup-12 | Show it for this year | create_plots; follow-up to: Plot weight over the last year. |
| followup-13 | Make it a bar chart | create_plots; follow-up to: Plot weight over the last year. |
| followup-14 | Show resting heart rate instead | create_plots; follow-up to: Plot weight over the last year. |
| readiness-01 | What is my training readiness today? | get_training_readiness |
| readiness-02 | Am I ready to train today? | get_training_readiness |
| readiness-03 | What was my readiness yesterday? | get_training_readiness |
| readiness-04 | Show my readiness for 2026-09-27. | get_training_readiness |
| readiness-05 | What is my projected readiness tomorrow? | get_projected_training_readiness |
| readiness-06 | Forecast training readiness for tomorrow. | get_projected_training_readiness |
| training-01 | I want to increase FTP. | preview_training_plan |
| training-02 | Help me build endurance. | preview_training_plan |
| training-03 | Plan my week around a hard three-hour cycling trip on Wednesday at 08:00. | preview_training_plan |
| training-04 | I want to stay in shape. | preview_training_plan |
| training-05 | Preview a training plan for the next 12 weeks. | preview_training_plan |
| training-06 | I want to improve FTP and have a hard 180 minute ride on Wednesday starting at 08:00. | preview_training_plan |
| training-07 | Build endurance with a running training plan. | preview_training_plan |
| training-08 | Adjust my training plan around a hard trip on Friday. | preview_training_plan |
| unsupported-01 | Plot body battery versus sleep score this year. | Which Body Battery |
| unsupported-02 | Plot weight with a rolling average. | How many days |
| unsupported-03 | Plot median weight. | daily, weekly or monthly |
| unsupported-04 | Plot weekly median weight and a 7-day rolling average. | separate plots |
| unsupported-05 | Plot sleep score versus blood glucose this year. | two supported metrics |
| unsupported-06 | Compare my latest ride with all rides. | Which period |
| model-01 | How were my steps? | Which period |
| model-02 | Have I been sleeping enough recently? | get_health_summary |
| model-03 | What data do you have about my rides? | list_activities |
| model-04 | Has my weight changed recently? | get_health_summary |
| model-05 | How has my HRV been lately? | get_health_summary |
| model-06 | Do I have any goals saved? | get_training_context |
| model-07 | What is missing from my training preferences? | get_training_context |
| model-08 | Was my latest ride effective? | assess_ride |
| model-09 | Show my running volume for the last four weeks. | running_volume_trend |
| model-10 | List my three most recent activities and available heart rate and power. | list_activities |
| model-11 | Can you plot metrics beyond the dashboard presets? | get_chart_catalog |
| model-12 | What measurements can I explore? | get_chart_catalog |
| multiplot-01 | Plot weight from 2026-01-01 to 2026-02-01 and steps from 2026-03-01 to 2026-04-01. | create_plots |
| multiplot-02 | Plot sleep score; plot steps; plot weight. | create_plots |
| multiplot-03 | Plot hydration this year; plot acute training load this month. | create_plots |
| multiplot-04 | Graph steps and weight this year. | create_plots |
| clarification-followup-01 | latest | create_plots; follow-up to: Plot body battery versus sleep score this year. |
| clarification-followup-02 | 7 days | create_plots; follow-up to: Plot weight with a rolling average this year. |
| clarification-followup-03 | weekly please | create_plots; follow-up to: Plot median weight this year. |
| clarification-followup-04 | last seven days | get_health_summary; follow-up to: How were my steps?; ['2026-10-05', '2026-10-11'] |
| benefit-01 | What was the main training benefit of my last ride? | compare_latest_ride |
| benefit-02 | What was the primary benefit of my latest ride? | compare_latest_ride |
| training-09 | I want two hard rides Tuesday and wedensday. Long ride on firday and I can train today. I want FTP improvement. | preview_training_plan |
| training-10 | Preview a training plan with a hard ride Tuesday for 3.5 hours and an easy ride Friday for 45 minutes. | preview_training_plan |
| default-comparison-09 | how was my ride compared to other rides in the kast 3 months? | compare_latest_ride; ['2026-07-11', '2026-10-11'] |
