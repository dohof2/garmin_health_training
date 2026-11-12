# Garmin Personal API research reference

Captured 9 November 2026 from the [official Swagger page](https://developer.garmin.com/gc-developer-program/personal/swagger-docs/). Public documentation only; no account data or credentials.

The viewer embeds its specification in the linked JavaScript bundle. The extracted JSON is preserved as [openapi-2026-11-09.json](openapi-2026-11-09.json).

OpenAPI 3.0.1; API version 1.0.0; 26 paths; 109 schemas.

SHA-256 of saved JSON: `6d271ee1fa9a092cb434c240c6ce48ef5180fdfe746f6846bf49643db421e4ba`.

Source bundle: `https://developer.garmin.com/component---src-pages-gc-developer-program-personal-swagger-docs-js-715115a6210d45afc282.js`

Authentication is documented separately in the [official guide](https://developer.garmin.com/gc-developer-program/personal/personal-api/) and [FAQ](https://developer.garmin.com/gc-developer-program/personal/personal-faq/). The resource schema does not describe the token POST.

| Method | Path | Contract description |
| --- | --- | --- |
| GET | `/activity-service/activity/{activityId}` | Retrieves the activity summary, metadata, measurements, and split summary information for the specified activity. |
| GET | `/activity-service/activity/{activityId}/workouts` | Retrieves workouts performed during an activity |
| GET | `/activitylist-service/activities/search/activities` | Searches activities using the supplied filters and returns matching paginated activity summaries. |
| GET | `/biometric-service/heartRateZones/v2` | Retrieve the user's heart rate zone configuration. |
| GET | `/download-service/files/activity/{activityId}` | Download an activity file in its original format. |
| GET | `/fitnessage-service/fitnessage/v2/{calendarDate}` | Returns the lastest Fitness Age information as of the target calendar date. |
| GET | `/goal-service/goal/user/effective/weightgoal/{startDate}/{endDate}` | Returns the authenticated user's effective weight goals and weight goal ranges for the requested date interval. |
| GET | `/hrv-service/hrv/{calendarDate}` | Get HRV data for a specific date |
| GET | `/hrv-service/hrv/daily/{fromDate}/{toDate}` | Get HRV daily summaries for a date range |
| GET | `/nutrition-service/food/logs/{date}` | Retrieves the user's daily nutrition summary for a specific calendar date. This includes the user's nutrition goals, nutrients consumed, and discrete events for the day. The response can optionally include meal-by-meal breakdowns of calories and other nutrients consumed by the user on the given date. |
| GET | `/periodichealth-service/menstrualcycle/summary/{calendarDate}` | Returns a summary of the user's menstrual cycle. |
| GET | `/periodichealth-service/menstrualcycle/dayview/{calendarDate}` | Returns detailed menstrual cycle information for a single calendar day, combining the user's logged daily data (symptoms, flow, mood, etc.), the cycle summary for that day, and (for pregnancy tracking) weekly weight goal ranges. |
| GET | `/sleep-service/sleep/dailySleep` | Retrieves daily sleep data for a calendar date |
| GET | `/sleep-service/sleep/dailySleepSummariesByDate` | Retrieves daily sleep summaries data for a date range, up to a maximum of 31 days. |
| GET | `/userprofile-service/userprofile/settings` | Retrieve the user profile settings. |
| GET | `/usersummary-service/stats/hydration/daily/{startDate}/{endDate}` | Get daily hydration data for a date range, up to a maximum of 31 days. |
| GET | `/usersummary-service/stats/steps/daily/{startDate}/{endDate}` | Get daily steps data for a date range, up to a maximum of 28 days. |
| GET | `/usersummary-service/stats/stress/daily/{startDate}/{endDate}` | Get daily stress data for a date range, up to a maximum of 28 days. |
| GET | `/usersummary-service/usersummary/daily` | Get user summary data for a specific date. User summary data includes steps, calories, stress, Body Battery, and other wellness metrics for the given date. |
| GET | `/usersummary-service/v2/dailysummaries` | Get user daily summaries for a date range, up to a maximum of 1 year. |
| GET | `/weight-service/weight/all/{startDate}/{endDate}` | Retrieve all weight entries for a specified date range. |
| GET | `/weight-service/weight/range/{startDate}/{endDate}` | Retrieve weight summaries for a date range, including daily latest weights, the range average, and adjacent weights. |
| GET | `/wellness-service/wellness/bodyBattery/reports/daily` | Returns daily Body Battery reports for a date range, up to a maximum of 31 days. |
| GET | `/wellness-service/wellness/daily/spo2acclimation/{calendarDate}` | Returns daily SpO2 readings data for a given calendar date. |
| GET | `/wellness-service/wellness/dailyHeartRate` | Returns daily heart rate data for a given date. |
| GET | `/wellnessactivity-service/activity/summary/range/{fromDate}/{untilDate}` | Returns a list of wellness activity summaries for the given date range. The fromDate and untilDate are inclusive. |

No resource write methods are present. A path with “workouts” reads activity-associated workouts; it is not a publication API. Recheck upstream before implementation.
