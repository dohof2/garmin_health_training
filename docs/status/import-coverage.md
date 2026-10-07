# Garmin Import Coverage

Last verified: 7 October 2026
Source: ignored local `data/imports/Garmin data.zip`
Archive SHA-256: `123d1083c5f783c2d0d0a821d7ee807f448aebbddb08a2eecb724e30e4fd393c`

## Result

All health, activity, training, workout, route, gear, goal, nutrition, and
biometric categories with a safe application meaning have been imported. The
original archive remains immutable. Repeat runs resume completed files and
write zero duplicate records.

| Coverage area | Imported result |
|---|---:|
| Activities | 1,058 |
| Daily metrics | 29,888 |
| Sleep metrics | 22,198 |
| Activity-detail samples | 2,912,230 |
| Monitoring health samples | 3,706,008 |
| Hydration events | 891 unique from 904 source rows |
| Abnormal-heart-rate events | 49 |
| Garmin daily nutrition summaries | 291 |
| Extended training/biometric records | 26,143 across 48 categories |

Extended records include training status/load, VO₂ max, race predictions,
fitness age, cycling ability, heat/altitude acclimation, body metrics, personal
records, heart-rate and power zones, workouts and schedules, training plans,
adaptive-coaching/metrics backups, routes, power guidance, goals, calendar
events, gear, Golf clubs, and Tacx workouts.

## File accounting

Every one of the 298 outer archive files has a recorded classification:

| Classification | Files | Meaning |
|---|---:|---|
| Imported by the extended stage | 144 | Parsed, sanitized, normalized, and checkpointed |
| Handled by dedicated importers | 121 | Activity/daily/sleep/wellness JSON and uploaded FIT/GPX/TCX containers |
| Intentionally excluded | 33 | Account, contact, consent, social, device-backup, subscription, media, or LiveTrack-location administration |
| Unsupported/unclassified | 0 | Nothing remains without an explicit decision |

The eight nested ZIPs are also accounted for. Garmin's official FIT SDK decoded
all 55,448 FIT files without failure. Semantically supported activity and
monitoring samples were normalized; training/metrics backup FIT records were
stored in the extended archive table. Remaining proprietary/configuration FIT
types were inventoried but are not copied as opaque numeric fields because they
cannot be represented reliably. The immutable source remains available for any
future parser improvement.

## Privacy and validation

- Normalized extended payloads recursively remove user-profile, owner, device,
  serial-number, and primary-device identifiers.
- Social posts/comments/likes, contact/account profiles, consent/forms, device
  backups, subscriptions, and LiveTrack locations are not duplicated into the
  application database.
- Course geometry and activity coordinates are retained locally because routes
  and activity analysis are explicitly in scope.
- Import checkpoints report zero failed or unmatched files.
- SQLite foreign-key and integrity checks pass.
- The dashboard coverage endpoint reports ten of ten implemented categories
  complete and 21,933 tracked files.
