import { useEffect, useState } from "react";

type HealthResponse = {
  status: string;
  database: string;
  schema: {
    migrations: number;
    tables: number;
  };
  version: string;
};

type HistorySummary = {
  data_mode: "empty" | "synthetic" | "mixed" | "real";
  activity_count: number;
  metric_count: number;
  activity_date_start: string | null;
  activity_date_end: string | null;
  latest_metric_at: string | null;
  latest_activity: null | {
    id: string;
    activity_type: string;
    name: string | null;
    started_at: string;
    duration_seconds: number | null;
    distance_meters: number | null;
    calories_kcal: number | null;
    source_name: string;
  };
  latest_steps: null | {
    value: number;
    unit: string;
    recorded_at: string;
    source_name: string;
  };
};

type Activity = {
  id: string;
  activity_type: string;
  name: string | null;
  started_at: string;
  ended_at: string | null;
  timezone: string | null;
  duration_seconds: number | null;
  distance_meters: number | null;
  calories_kcal: number | null;
  elevation_gain_meters: number | null;
  source_name: string;
};

type ActivityDetail = Activity & {
  sample_summary: {
    sample_count: number;
    first_sample_at: string | null;
    last_sample_at: string | null;
    average_heart_rate_bpm: number | null;
    maximum_heart_rate_bpm: number | null;
    average_power_watts: number | null;
    maximum_power_watts: number | null;
    maximum_speed_mps: number | null;
  };
};

type ActivityState =
  | { kind: "idle" | "loading"; items: Activity[] }
  | { kind: "ready"; items: Activity[] }
  | { kind: "error"; items: Activity[]; message: string };

type ActivityDetailState =
  | { kind: "closed" }
  | { kind: "loading"; activityId: string }
  | { kind: "ready"; activity: ActivityDetail }
  | { kind: "error"; activityId: string; message: string };

type WeeklyCalories = {
  basis: "latest_available_garmin_week";
  week_start: string;
  week_end: string;
  days_expected: number;
  days_with_data: number;
  missing_dates: string[];
  is_complete: boolean;
  total_kcal: number;
  active_kcal: number;
  resting_kcal: number;
  source_name: "garmin_export";
};

type ImportCoverage = {
  archive_imported_at: string | null;
  summary: {
    categories: number;
    complete_categories: number;
    attention_categories: number;
    tracked_files: number;
    failed_files: number;
    unmatched_files: number;
  };
  categories: Array<{
    id: string;
    label: string;
    status: "complete" | "attention" | "empty";
    records: number;
    files: null | {
      completed: number;
      failed: number;
      unmatched: number;
    };
    date_start: string | null;
    date_end: string | null;
    note: string;
  }>;
  failures: Array<{
    category: string;
    member_name: string;
    status: string;
    error_message: string | null;
  }>;
  archive_catalog: {
    total_files: number;
    imported: number;
    handled_elsewhere: number;
    excluded: number;
    unsupported: number;
  };
};

type ConnectionState =
  | { kind: "checking" }
  | {
      kind: "ready";
      health: HealthResponse;
      summary: HistorySummary;
      weeklyCalories: WeeklyCalories | null;
      coverage: ImportCoverage;
    }
  | { kind: "offline" };

type GarminPreview = {
  ready: boolean;
  archive: {
    name: string;
    archive_bytes: number;
    nested_archives: number;
  };
  activities: {
    count: number;
    date_start: string;
    date_end: string;
  };
  daily_metrics: {
    count: number;
    date_start: string;
    date_end: string;
  };
  sleep_metrics: {
    count: number;
    date_start: string | null;
    date_end: string | null;
  };
};

type GarminImportResult = {
  status: "completed";
  activities: { total: number; created: number; updated: number };
  daily_metrics: { total: number; created: number; updated: number };
  sleep_metrics: { total: number; created: number; updated: number };
};

type ImportState =
  | { kind: "idle" }
  | { kind: "loading" }
  | { kind: "preview"; preview: GarminPreview }
  | { kind: "importing"; preview: GarminPreview }
  | { kind: "complete"; preview: GarminPreview; result: GarminImportResult }
  | { kind: "error"; message: string };

const foundations = [
  {
    label: "Interface",
    title: "React + TypeScript",
    detail: "Local, responsive application shell",
  },
  {
    label: "API",
    title: "Python + FastAPI",
    detail: "Local backend on 127.0.0.1",
  },
  {
    label: "Storage",
    title: "SQLite",
    detail: "Versioned schema stored only on this computer",
  },
];

const formatShortDate = (value: string) =>
  new Intl.DateTimeFormat(undefined, { month: "short", day: "numeric" }).format(
    new Date(`${value}T00:00:00`),
  );

const formatLongDate = (value: string) =>
  new Intl.DateTimeFormat(undefined, {
    year: "numeric",
    month: "short",
    day: "numeric",
  }).format(new Date(`${value.slice(0, 10)}T00:00:00`));

const shiftDate = (value: string, days: number) => {
  const date = new Date(`${value.slice(0, 10)}T00:00:00Z`);
  date.setUTCDate(date.getUTCDate() + days);
  return date.toISOString().slice(0, 10);
};

const sourceLabel = (sourceName: string) =>
  sourceName === "garmin_export"
    ? "Garmin export"
    : sourceName === "synthetic_fixture"
      ? "Synthetic fixture"
      : sourceName.replaceAll("_", " ");

const formatDuration = (seconds: number | null) => {
  if (seconds === null) return "Not recorded";
  const roundedMinutes = Math.round(seconds / 60);
  const hours = Math.floor(roundedMinutes / 60);
  const minutes = roundedMinutes % 60;
  return hours ? `${hours}h ${minutes}m` : `${minutes} min`;
};

type DateRangeFilterProps = {
  start: string;
  end: string;
  minimum: string | null;
  maximum: string | null;
  onChange: (start: string, end: string) => void;
};

function DateRangeFilter({
  start,
  end,
  minimum,
  maximum,
  onChange,
}: DateRangeFilterProps) {
  const setPreset = (days: number | null) => {
    if (!maximum) return;
    if (days === null) {
      if (minimum) onChange(minimum, maximum);
      return;
    }
    onChange(shiftDate(maximum, -(days - 1)), maximum);
  };

  return (
    <div className="date-filter" aria-label="Activity date range">
      <div className="date-inputs">
        <label>
          From
          <input
            type="date"
            value={start}
            min={minimum ?? undefined}
            max={end || maximum || undefined}
            onChange={(event) => onChange(event.target.value, end)}
          />
        </label>
        <label>
          To
          <input
            type="date"
            value={end}
            min={start || minimum || undefined}
            max={maximum ?? undefined}
            onChange={(event) => onChange(start, event.target.value)}
          />
        </label>
      </div>
      <div className="date-presets" aria-label="Date range presets">
        <button type="button" onClick={() => setPreset(30)}>30 days</button>
        <button type="button" onClick={() => setPreset(90)}>90 days</button>
        <button type="button" onClick={() => setPreset(null)}>All</button>
      </div>
    </div>
  );
}

function ActivityDetailPanel({ activity }: { activity: ActivityDetail }) {
  const summary = activity.sample_summary;
  const details = [
    ["Duration", formatDuration(activity.duration_seconds)],
    [
      "Distance",
      activity.distance_meters === null
        ? "Not recorded"
        : `${(activity.distance_meters / 1000).toFixed(1)} km`,
    ],
    [
      "Calories",
      activity.calories_kcal === null
        ? "Not recorded"
        : `${Math.round(activity.calories_kcal).toLocaleString()} kcal`,
    ],
    [
      "Elevation gain",
      activity.elevation_gain_meters === null
        ? "Not recorded"
        : `${Math.round(activity.elevation_gain_meters).toLocaleString()} m`,
    ],
    [
      "Average heart rate",
      summary.average_heart_rate_bpm === null
        ? "Not recorded"
        : `${Math.round(summary.average_heart_rate_bpm)} bpm`,
    ],
    [
      "Maximum heart rate",
      summary.maximum_heart_rate_bpm === null
        ? "Not recorded"
        : `${Math.round(summary.maximum_heart_rate_bpm)} bpm`,
    ],
    [
      "Average power",
      summary.average_power_watts === null
        ? "Not recorded"
        : `${Math.round(summary.average_power_watts)} W`,
    ],
    [
      "Maximum speed",
      summary.maximum_speed_mps === null
        ? "Not recorded"
        : `${(summary.maximum_speed_mps * 3.6).toFixed(1)} km/h`,
    ],
  ];

  return (
    <div className="activity-detail">
      <div className="activity-detail-grid">
        {details.map(([label, value]) => (
          <div key={label}>
            <span>{label}</span>
            <strong className={value === "Not recorded" ? "missing-value" : ""}>
              {value}
            </strong>
          </div>
        ))}
      </div>
      <p>
        {summary.sample_count.toLocaleString()} detailed samples · {sourceLabel(activity.source_name)}
        {activity.timezone ? ` · ${activity.timezone}` : " · timezone not recorded"}
      </p>
    </div>
  );
}

export default function App() {
  const [connection, setConnection] = useState<ConnectionState>({
    kind: "checking",
  });
  const [importState, setImportState] = useState<ImportState>({ kind: "idle" });
  const [activityRange, setActivityRange] = useState({ start: "", end: "" });
  const [activityState, setActivityState] = useState<ActivityState>({
    kind: "idle",
    items: [],
  });
  const [activityDetail, setActivityDetail] = useState<ActivityDetailState>({
    kind: "closed",
  });

  useEffect(() => {
    const controller = new AbortController();

    Promise.all([
      fetch("/api/health", { signal: controller.signal }),
      fetch("/api/history/summary", { signal: controller.signal }),
      fetch("/api/history/weekly-calories", { signal: controller.signal }),
      fetch("/api/imports/coverage", { signal: controller.signal }),
    ])
      .then(async ([healthResponse, summaryResponse, weeklyResponse, coverageResponse]) => {
        if (
          !healthResponse.ok ||
          !summaryResponse.ok ||
          !weeklyResponse.ok ||
          !coverageResponse.ok
        ) {
          throw new Error("Backend is unavailable");
        }
        const [health, summary, weeklyCalories, coverage] = await Promise.all([
          healthResponse.json() as Promise<HealthResponse>,
          summaryResponse.json() as Promise<HistorySummary>,
          weeklyResponse.json() as Promise<WeeklyCalories | null>,
          coverageResponse.json() as Promise<ImportCoverage>,
        ]);
        setConnection({ kind: "ready", health, summary, weeklyCalories, coverage });
        if (summary.activity_date_end) {
          setActivityRange((current) =>
            current.end
              ? current
              : {
                  start: shiftDate(summary.activity_date_end!, -29),
                  end: summary.activity_date_end!,
                },
          );
        }
      })
      .catch((error: unknown) => {
        if (error instanceof DOMException && error.name === "AbortError") return;
        setConnection({ kind: "offline" });
      });

    return () => controller.abort();
  }, []);

  useEffect(() => {
    if (!activityRange.start || !activityRange.end) return;
    if (activityRange.start > activityRange.end) {
      setActivityState({
        kind: "error",
        items: [],
        message: "The start date must be on or before the end date.",
      });
      return;
    }

    const controller = new AbortController();
    const parameters = new URLSearchParams({
      limit: "50",
      start_date: activityRange.start,
      end_date: activityRange.end,
    });
    setActivityState((current) => ({ kind: "loading", items: current.items }));
    setActivityDetail({ kind: "closed" });

    fetch(`/api/activities?${parameters.toString()}`, {
      signal: controller.signal,
    })
      .then(async (response) => {
        if (!response.ok) throw new Error("Activities could not be loaded.");
        return response.json() as Promise<Activity[]>;
      })
      .then((items) => setActivityState({ kind: "ready", items }))
      .catch((error: unknown) => {
        if (error instanceof DOMException && error.name === "AbortError") return;
        setActivityState({
          kind: "error",
          items: [],
          message: error instanceof Error ? error.message : "Activities could not be loaded.",
        });
      });

    return () => controller.abort();
  }, [activityRange.start, activityRange.end]);

  const statusText =
    connection.kind === "ready"
      ? `Connected · ${connection.health.schema.tables} database tables`
      : connection.kind === "offline"
        ? "Backend is not running"
        : "Checking local backend…";

  const summary = connection.kind === "ready" ? connection.summary : null;
  const weeklyCalories =
    connection.kind === "ready" ? connection.weeklyCalories : null;
  const coverage = connection.kind === "ready" ? connection.coverage : null;
  const dataModeLabel =
    summary?.data_mode === "synthetic"
      ? "Synthetic data · not Garmin data"
      : summary?.data_mode === "mixed"
        ? "Mixed data · Garmin + synthetic fixture"
        : summary?.data_mode === "real"
          ? "Garmin data"
          : null;

  const toggleActivityDetail = async (activityId: string) => {
    if (
      (activityDetail.kind === "ready" && activityDetail.activity.id === activityId) ||
      (activityDetail.kind === "loading" && activityDetail.activityId === activityId)
    ) {
      setActivityDetail({ kind: "closed" });
      return;
    }

    setActivityDetail({ kind: "loading", activityId });
    try {
      const response = await fetch(`/api/activities/${encodeURIComponent(activityId)}`);
      if (!response.ok) throw new Error("Activity details could not be loaded.");
      const activity = (await response.json()) as ActivityDetail;
      setActivityDetail({ kind: "ready", activity });
    } catch (error: unknown) {
      setActivityDetail({
        kind: "error",
        activityId,
        message: error instanceof Error ? error.message : "Activity details could not be loaded.",
      });
    }
  };

  const readError = async (response: Response) => {
    try {
      const payload = (await response.json()) as { detail?: string };
      return payload.detail ?? "The Garmin import request failed.";
    } catch {
      return "The Garmin import request failed.";
    }
  };

  const previewGarmin = async () => {
    setImportState({ kind: "loading" });
    try {
      const response = await fetch("/api/imports/garmin/preview");
      if (!response.ok) throw new Error(await readError(response));
      const preview = (await response.json()) as GarminPreview;
      setImportState({ kind: "preview", preview });
    } catch (error: unknown) {
      setImportState({
        kind: "error",
        message: error instanceof Error ? error.message : "Preview failed.",
      });
    }
  };

  const importGarmin = async (preview: GarminPreview) => {
    setImportState({ kind: "importing", preview });
    try {
      const response = await fetch("/api/imports/garmin?confirm=true", {
        method: "POST",
      });
      if (!response.ok) throw new Error(await readError(response));
      const result = (await response.json()) as GarminImportResult;
      setImportState({ kind: "complete", preview, result });

      const [summaryResponse, weeklyResponse, coverageResponse] = await Promise.all([
        fetch("/api/history/summary"),
        fetch("/api/history/weekly-calories"),
        fetch("/api/imports/coverage"),
      ]);
      if (summaryResponse.ok && weeklyResponse.ok && coverageResponse.ok) {
        const [refreshedSummary, refreshedWeeklyCalories, refreshedCoverage] = await Promise.all([
          summaryResponse.json() as Promise<HistorySummary>,
          weeklyResponse.json() as Promise<WeeklyCalories | null>,
          coverageResponse.json() as Promise<ImportCoverage>,
        ]);
        setConnection((current) =>
          current.kind === "ready"
            ? {
                ...current,
                summary: refreshedSummary,
                weeklyCalories: refreshedWeeklyCalories,
                coverage: refreshedCoverage,
              }
            : current,
        );
      }
    } catch (error: unknown) {
      setImportState({
        kind: "error",
        message: error instanceof Error ? error.message : "Import failed.",
      });
    }
  };
  const previewCards = [
    {
      label: "Latest steps",
      value: summary?.latest_steps
        ? Math.round(summary.latest_steps.value).toLocaleString()
        : "—",
      detail: summary?.latest_steps ? "Daily total" : "No step data loaded",
      subdetail: summary?.latest_steps
        ? `${sourceLabel(summary.latest_steps.source_name)} · as of ${formatLongDate(summary.latest_steps.recorded_at)}`
        : undefined,
      tooltip: "The most recent daily step total available from the stored history.",
    },
    {
      label: "Last activity",
      value: summary?.latest_activity?.name ?? "—",
      detail: summary?.latest_activity
        ? summary.latest_activity.activity_type.replaceAll("_", " ")
        : "No activities loaded",
      subdetail: summary?.latest_activity
        ? `${sourceLabel(summary.latest_activity.source_name)} · ${formatLongDate(summary.latest_activity.started_at)}`
        : undefined,
      tooltip: "The most recently started activity available from the stored history.",
    },
    {
      label: "Weekly calories burned",
      value: weeklyCalories
        ? `${Math.round(weeklyCalories.total_kcal).toLocaleString()} kcal`
        : "—",
      detail: weeklyCalories
        ? `${Math.round(weeklyCalories.active_kcal).toLocaleString()} active · ${Math.round(weeklyCalories.resting_kcal).toLocaleString()} resting`
        : "No Garmin calorie data loaded",
      subdetail: weeklyCalories
        ? `${sourceLabel(weeklyCalories.source_name)} · ${formatShortDate(weeklyCalories.week_start)}–${formatShortDate(weeklyCalories.week_end)} · ${weeklyCalories.is_complete ? "complete week" : `partial week (${weeklyCalories.days_with_data}/${weeklyCalories.days_expected} days)`}`
        : undefined,
      tooltip: weeklyCalories?.missing_dates.length
        ? `Missing daily totals: ${weeklyCalories.missing_dates.map(formatLongDate).join(", ")}. Missing days are not counted as zero.`
        : "Total calories burned, split into Garmin active and resting calories.",
    },
  ];

  return (
    <main>
      <header className="hero">
        <p className="eyebrow">Personal health workspace</p>
        <h1>Your training history,<br />kept close.</h1>
        <p className="intro">
          The local foundation and first Garmin importer are ready. Your source
          archive stays private while normalized history powers this dashboard.
        </p>
        <div className={`connection connection--${connection.kind}`}>
          <span aria-hidden="true" />
          {statusText}
        </div>
      </header>

      <section className="preview" aria-labelledby="preview-title">
        <div className="section-heading">
          <div>
            <p>Data preview</p>
            <h2 id="preview-title">A safe dataset to build on</h2>
          </div>
          {dataModeLabel && <div className="synthetic-label">{dataModeLabel}</div>}
        </div>
        <div className="preview-grid">
          {previewCards.map((card) => (
            <article className="data-card" key={card.label}>
              <p>
                {card.label}{" "}
                <abbr className="info-tip" title={card.tooltip} aria-label={card.tooltip}>i</abbr>
              </p>
              <h3>{card.value}</h3>
              <span>{card.detail}</span>
              {card.subdetail && <small>{card.subdetail}</small>}
            </article>
          ))}
        </div>
      </section>

      <section className="activities" aria-labelledby="activities-title">
        <div className="section-heading activities-heading">
          <div>
            <p>Activity history</p>
            <h2 id="activities-title">Explore the details</h2>
          </div>
          <DateRangeFilter
            start={activityRange.start}
            end={activityRange.end}
            minimum={summary?.activity_date_start ?? null}
            maximum={summary?.activity_date_end ?? null}
            onChange={(start, end) => setActivityRange({ start, end })}
          />
        </div>

        {activityState.kind === "loading" && activityState.items.length === 0 && (
          <p className="activity-message">Loading activities…</p>
        )}
        {activityState.kind === "error" && (
          <p className="activity-message activity-message--error">{activityState.message}</p>
        )}
        {activityState.kind === "ready" && activityState.items.length === 0 && (
          <p className="activity-message">No activities were recorded in this date range.</p>
        )}
        {activityState.items.length > 0 && (
          <div className="activity-list">
            <div className="activity-list-summary">
              <span>
                {activityState.items.length.toLocaleString()}
                {activityState.items.length === 50 ? " most recent " : " "}
                {activityState.items.length === 1 ? "activity" : "activities"}
              </span>
              {activityState.kind === "loading" && <span>Refreshing…</span>}
            </div>
            {activityState.items.map((activity) => {
              const isOpen =
                (activityDetail.kind === "ready" && activityDetail.activity.id === activity.id) ||
                (activityDetail.kind === "loading" && activityDetail.activityId === activity.id) ||
                (activityDetail.kind === "error" && activityDetail.activityId === activity.id);
              const summaryParts = [
                formatDuration(activity.duration_seconds),
                activity.distance_meters === null
                  ? null
                  : `${(activity.distance_meters / 1000).toFixed(1)} km`,
                activity.calories_kcal === null
                  ? null
                  : `${Math.round(activity.calories_kcal).toLocaleString()} kcal`,
              ].filter((item): item is string => item !== null);

              return (
                <article className="activity-row" key={activity.id}>
                  <button
                    className="activity-toggle"
                    type="button"
                    aria-expanded={isOpen}
                    onClick={() => void toggleActivityDetail(activity.id)}
                  >
                    <span className="activity-date">{formatLongDate(activity.started_at)}</span>
                    <span className="activity-name">
                      <strong>{activity.name ?? activity.activity_type.replaceAll("_", " ")}</strong>
                      <small>{activity.activity_type.replaceAll("_", " ")} · {sourceLabel(activity.source_name)}</small>
                    </span>
                    <span className="activity-summary">{summaryParts.join(" · ") || "Summary not recorded"}</span>
                    <span className="activity-chevron" aria-hidden="true">{isOpen ? "−" : "+"}</span>
                  </button>
                  {activityDetail.kind === "loading" && activityDetail.activityId === activity.id && (
                    <p className="activity-detail-message">Loading recorded details…</p>
                  )}
                  {activityDetail.kind === "error" && activityDetail.activityId === activity.id && (
                    <p className="activity-detail-message activity-message--error">{activityDetail.message}</p>
                  )}
                  {activityDetail.kind === "ready" && activityDetail.activity.id === activity.id && (
                    <ActivityDetailPanel activity={activityDetail.activity} />
                  )}
                </article>
              );
            })}
          </div>
        )}
      </section>

      <section className="coverage" aria-labelledby="coverage-title">
        <div className="section-heading">
          <div>
            <p>Import coverage</p>
            <h2 id="coverage-title">What is safely loaded</h2>
          </div>
          {coverage && (
            <div
              className={`coverage-overall ${coverage.summary.attention_categories ? "coverage-overall--attention" : ""}`}
            >
              {coverage.summary.complete_categories} of {coverage.summary.categories} complete
            </div>
          )}
        </div>

        {!coverage && (
          <p className="import-copy">Waiting for the local coverage report…</p>
        )}
        {coverage && (
          <>
            <div className="coverage-summary">
              <span>{coverage.summary.tracked_files.toLocaleString()} tracked files</span>
              <span>{coverage.summary.failed_files.toLocaleString()} failed</span>
              <span>{coverage.summary.unmatched_files.toLocaleString()} unmatched</span>
              <span>{coverage.archive_catalog.total_files.toLocaleString()} outer archive files accounted for</span>
            </div>
            <div className="coverage-list">
              {coverage.categories.map((category) => (
                <article className="coverage-row" key={category.id}>
                  <div className="coverage-main">
                    <div>
                      <span className={`coverage-status coverage-status--${category.status}`}>
                        {category.status}
                      </span>
                      <h3>{category.label}</h3>
                    </div>
                    <strong>{category.records.toLocaleString()}</strong>
                  </div>
                  <p>{category.note}</p>
                  <div className="coverage-meta">
                    <span>
                      {category.date_start?.slice(0, 10) ?? "No start date"} → {category.date_end?.slice(0, 10) ?? "No end date"}
                    </span>
                    {category.files && (
                      <span>
                        {category.files.completed.toLocaleString()} files complete
                        {(category.files.failed > 0 || category.files.unmatched > 0) &&
                          ` · ${category.files.failed} failed · ${category.files.unmatched} unmatched`}
                      </span>
                    )}
                  </div>
                </article>
              ))}
            </div>
            {coverage.failures.length > 0 && (
              <div className="coverage-failures" role="alert">
                <strong>Files requiring attention</strong>
                {coverage.failures.map((failure) => (
                  <p key={`${failure.category}-${failure.member_name}`}>
                    {failure.member_name}: {failure.error_message ?? failure.status}
                  </p>
                ))}
              </div>
            )}
          </>
        )}
      </section>

      <section className="import" aria-labelledby="import-title">
        <div className="section-heading">
          <div>
            <p>Garmin import</p>
            <h2 id="import-title">Review before writing</h2>
          </div>
          <button
            type="button"
            onClick={() => void previewGarmin()}
            disabled={importState.kind === "loading" || importState.kind === "importing"}
          >
            {importState.kind === "loading" ? "Checking ZIP…" : "Review local ZIP"}
          </button>
        </div>

        {importState.kind === "idle" && (
          <p className="import-copy">
            Run a read-only safety check and inspect counts before importing the
            original ZIP. The source archive is never changed.
          </p>
        )}
        {importState.kind === "error" && (
          <p className="import-message import-message--error">{importState.message}</p>
        )}
        {(importState.kind === "preview" ||
          importState.kind === "importing" ||
          importState.kind === "complete") && (
          <div className="import-results">
            <div>
              <span>Archive</span>
              <strong>{importState.preview.archive.name}</strong>
              <small>
                {(importState.preview.archive.archive_bytes / 1024 / 1024).toFixed(1)} MiB · {importState.preview.archive.nested_archives} nested ZIPs
              </small>
            </div>
            <div>
              <span>Activities</span>
              <strong>{importState.preview.activities.count.toLocaleString()}</strong>
              <small>{importState.preview.activities.date_start.slice(0, 10)} → {importState.preview.activities.date_end.slice(0, 10)}</small>
            </div>
            <div>
              <span>Daily metrics</span>
              <strong>{importState.preview.daily_metrics.count.toLocaleString()}</strong>
              <small>{importState.preview.daily_metrics.date_start} → {importState.preview.daily_metrics.date_end}</small>
            </div>
            <div>
              <span>Sleep metrics</span>
              <strong>{importState.preview.sleep_metrics.count.toLocaleString()}</strong>
              <small>{importState.preview.sleep_metrics.date_start ?? "—"} → {importState.preview.sleep_metrics.date_end ?? "—"}</small>
            </div>
          </div>
        )}
        {importState.kind === "preview" && (
          <button
            className="import-action"
            type="button"
            onClick={() => void importGarmin(importState.preview)}
          >
            Import reviewed records
          </button>
        )}
        {importState.kind === "importing" && (
          <p className="import-message">Importing in one database transaction…</p>
        )}
        {importState.kind === "complete" && (
          <p className="import-message import-message--success">
            Import complete: {importState.result.activities.created.toLocaleString()} new activities, {importState.result.daily_metrics.created.toLocaleString()} new daily metrics, and {importState.result.sleep_metrics.created.toLocaleString()} new sleep metrics. Existing records updated safely: {(
              importState.result.activities.updated +
              importState.result.daily_metrics.updated +
              importState.result.sleep_metrics.updated
            ).toLocaleString()}.
          </p>
        )}
      </section>

      <section className="foundation" aria-labelledby="foundation-title">
        <div className="section-heading">
          <p>Foundation 01</p>
          <h2 id="foundation-title">Local by design</h2>
        </div>
        <div className="cards">
          {foundations.map((foundation, index) => (
            <article key={foundation.title}>
              <div className="card-number">0{index + 1}</div>
              <p>{foundation.label}</p>
              <h3>{foundation.title}</h3>
              <span>{foundation.detail}</span>
            </article>
          ))}
        </div>
      </section>
    </main>
  );
}
