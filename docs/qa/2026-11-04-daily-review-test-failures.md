# Full backend test failures — November 4, 2026

Observed full run: 776 tests; 744 passed; 18 assertion failures and 14 errors. The two failing gap-day subtests are counted separately, as in unittest’s result.

The separate focused run covering this daily-review change passed 113 tests. The frontend build passed. No pre-change baseline run was made, so this report does not establish which failures predated the change.

Many saved-draft errors stop at `ValueError: Planning context changed; preview the week again before saving`. This is a shared failure point, not a demonstrated root cause for every listed test.

## backend/tests/test_ai_tools.py — AIToolTests

- **failure**: `test_catalog_exposes_only_scoped_read_only_tools`

## backend/tests/test_coach_remediation.py — CoachWorkflowTests

- **failure**: `test_long_slots_generate_more_than_two_hours`
- **failure**: `test_recovery_adapts_dose_preserving_goal_and_block`

## backend/tests/test_coach_remediation.py — PrescriptionTests

- **failure**: `test_numeric_ftp_laps_and_exact_total`

## backend/tests/test_coach_remediation.py — RegistryTests

- **failure**: `test_new_tools_dispatch_without_missing_registry_entries`

## backend/tests/test_sync.py — SyncTests

- **failure**: `test_catches_up_two_ten_and_thirty_day_gaps_including_empty_days [gap_days=2]`
- **failure**: `test_catches_up_two_ten_and_thirty_day_gaps_including_empty_days [gap_days=10]`
- **failure**: `test_open_session_schedule_runs_only_when_due`
- **failure**: `test_same_day_refresh_rechecks_every_stream_and_recovers_late_sleep`

## backend/tests/test_trainer_section_qc.py — TrainerSectionQC

- **failure**: `test_friday_long_ride_gets_budget_before_shorter_weekdays`

## backend/tests/test_training.py — TrainingTests

- **failure**: `test_api_requires_review_and_validates_preferences`
- **failure**: `test_changed_sports_requires_experience_and_volume_for_new_sport`
- **failure**: `test_dst_ambiguous_schedule_is_not_guessed`
- **failure**: `test_partial_answers_reused_and_only_missing_or_stale_asked`
- **failure**: `test_zero_minutes_never_gets_invented_as_volume`
- **error**: `test_date_filtered_exports_limit_feedback_and_workout_revisions`
- **error**: `test_draft_balances_sports_obeys_time_and_needs_explicit_accept`
- **error**: `test_feedback_preserved_revisions_without_silent_rewrite`
- **error**: `test_full_availability_reserves_a_day_and_restore_checks_conflicts`
- **error**: `test_portability_preserves_preferences_sessions_and_feedback`
- **error**: `test_priority_and_recovery_across_week_boundaries`
- **error**: `test_progression_needs_two_complete_weeks_and_explicit_review`
- **error**: `test_recent_pain_feedback_needs_explicit_reconfirmation`
- **error**: `test_repeat_draft_conflict_rolls_back_and_existing_profile_not_required`
- **error**: `test_session_edits_cannot_exceed_constraints_or_missing_equipment`
- **error**: `test_stale_profile_blocks_draft_and_accept_after_changed_preferences`
- **error**: `test_strength_has_recovery_day_and_draft_dates_validated`

## backend/tests/test_training_date_only.py — DateOnlyTests

- **failure**: `test_date_only_day_budget_conflict_does_not_pretend_clock_overlap`
- **failure**: `test_explicit_timed_availability_retains_original_clock`
- **error**: `test_date_only_preview_edit_and_schedule_patch_preserve_optional_clock`
- **error**: `test_optional_time_today_is_not_discarded_because_internal_anchor_passed`

## backend/tests/test_training_questionnaire.py — QuestionnaireTests

- **failure**: `test_beginner_zero_capacity_uses_supported_alternatives_and_can_activate`
