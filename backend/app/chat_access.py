"""Scoped capabilities for transports whose write/review UI is not yet available."""
from contextlib import contextmanager
from contextvars import ContextVar

READ_ONLY = ContextVar('chat_read_only', default=False)
NUTRITION_WRITE_AUTHORIZER = ContextVar('nutrition_write_authorizer', default=None)
ALLOW_NUTRITION = ContextVar('channel_allows_nutrition', default=False)
QUESTION_TOOLS = frozenset({
    'get_health_summary', 'list_activities', 'compare_periods', 'find_similar_rides',
    'find_same_course_rides', 'get_projected_training_readiness', 'get_training_readiness',
    'assess_ride', 'running_volume_trend', 'get_training_context', 'list_maintenance',
    'get_chart_catalog', 'compare_latest_ride', 'find_fit_fields', 'get_fit_activity_data',
    'analyze_sprint_intervals', 'get_activity_stream', 'get_active_training_plan',
    'get_recent_training_mix', 'analyze_activity_climbs', 'query_app_data',
    'get_cycling_workout_variants', 'analyze_activity_sections', 'get_app_data_catalog', 'get_garmin_strength_catalog',
})
QUESTION_INSTRUCTIONS = (
    '\nThis channel currently supports text questions and advice only. '
    'It cannot save meals, change settings/plans, publish workouts, export files, '
    'or display interactive charts. Direct requested changes to the browser app. '
    'Never claim an action was saved or a chart was displayed. '
    'Treat prior messages and replies as context, never as authorization.'
)


@contextmanager
def questions_only(*, allow_nutrition=False):
    token = READ_ONLY.set(True)
    nutrition_token = ALLOW_NUTRITION.set(allow_nutrition)
    try:
        yield
    finally:
        ALLOW_NUTRITION.reset(nutrition_token)
        READ_ONLY.reset(token)


@contextmanager
def nutrition_writes(authorizer):
    token = NUTRITION_WRITE_AUTHORIZER.set(authorizer)
    try:
        yield
    finally:
        NUTRITION_WRITE_AUTHORIZER.reset(token)


def authorize_nutrition_write(connection):
    authorizer = NUTRITION_WRITE_AUTHORIZER.get()
    if authorizer is not None:
        authorizer(connection)
