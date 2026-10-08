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
    local_date: string;
    timezone_used: string | null;
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
  local_date: string;
  timezone_used: string | null;
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

type DashboardCardId = "latest_steps" | "last_activity" | "weekly_calories";

type DashboardCardLayout = {
  id: DashboardCardId;
  card_type: string;
  label: string;
  position: number;
  is_visible: boolean;
};

type PreviewCard = {
  id: DashboardCardId;
  label: string;
  value: string;
  detail: string;
  subdetail?: string;
  tooltip: string;
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

type SyncCheckpoint = {
  data_type: string;
  coverage_start: string | null;
  coverage_end: string | null;
  seeded_from_import: number;
  last_attempt_at: string | null;
  last_success_at: string | null;
  status: "pending" | "syncing" | "synced" | "failed" | "reconnect_required";
  error_message: string | null;
};

type SyncStatus = {
  provider: string;
  connection_status: "not_connected" | "connected" | "reconnect_required";
  schedule_enabled: boolean;
  schedule_scope: "open_app_session_only";
  overlap_days: number;
  supports_updated_since: boolean;
  checkpoints: SyncCheckpoint[];
  verified_empty_intervals: number;
  last_job: null | {
    id: string;
    status: string;
    progress_current: number;
    progress_total: number | null;
    finished_at: string | null;
    error_message?: string | null;
    checkpoint?: {
      trigger?: string;
      totals?: { created: number; updated: number; unchanged: number; received: number };
      failures?: Array<{ data_type: string; date: string; error: string }>;
    };
  };
  live_sync_ready: boolean;
  next_action: string;
};

type SyncPlan = {
  through_date: string;
  total_intervals: number;
  limitation: string;
  data_types: Array<{
    data_type: string;
    start_date: string | null;
    end_date: string | null;
    days: number;
    overlap_days: number;
    kind: string;
    coverage_end: string | null;
  }>;
};

type GarminConnection = {
  status: "not_connected" | "connected" | "reconnect_required" | "mfa_required";
  has_saved_session: boolean;
  mfa_pending: boolean;
  token_storage: "local_private_file";
  updated_at: string;
};

type ConnectionState =
  | { kind: "checking" }
  | {
      kind: "ready";
      health: HealthResponse;
      summary: HistorySummary;
      weeklyCalories: WeeklyCalories | null;
      dashboardCards: DashboardCardLayout[];
      coverage: ImportCoverage;
      originalActivities: OriginalActivityInventory;
      syncStatus: SyncStatus;
      syncPlan: SyncPlan;
      garminConnection: GarminConnection;
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

type OriginalActivityInventory = {
  files: number;
  bytes: number;
  formats: Record<string, number>;
  available: boolean;
};

type RestorePreview = {
  ready: true;
  schema_version: number;
  created_at: string | null;
  table_counts: Record<string, number>;
  originals: { included: boolean; count: number };
  credentials_included: false;
  message: string;
};

type RestoreState =
  | { kind: "idle" }
  | { kind: "loading"; filename: string }
  | { kind: "ready"; filename: string; preview: RestorePreview }
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

const browserTimeZone =
  Intl.DateTimeFormat().resolvedOptions().timeZone || "UTC";

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
        {activity.timezone_used
          ? ` · dates shown in ${activity.timezone_used}`
          : " · timezone not recorded"}
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
  const [isCustomizingCards, setIsCustomizingCards] = useState(false);
  const [isSavingCards, setIsSavingCards] = useState(false);
  const [cardLayoutError, setCardLayoutError] = useState<string | null>(null);
  const [includeOriginalsInBackup, setIncludeOriginalsInBackup] = useState(false);
  const [restoreState, setRestoreState] = useState<RestoreState>({ kind: "idle" });
  const [syncMessage, setSyncMessage] = useState<string | null>(null);
  const [isSyncing, setIsSyncing] = useState(false);
  const [garminEmail, setGarminEmail] = useState("");
  const [garminPassword, setGarminPassword] = useState("");
  const [garminMfaCode, setGarminMfaCode] = useState("");
  const [isConnectingGarmin, setIsConnectingGarmin] = useState(false);
  const [connectionMessage, setConnectionMessage] = useState<string | null>(null);

  useEffect(() => {
    const controller = new AbortController();

    Promise.all([
      fetch("/api/health", { signal: controller.signal }),
      fetch(`/api/history/summary?timezone=${encodeURIComponent(browserTimeZone)}`, {
        signal: controller.signal,
      }),
      fetch("/api/history/weekly-calories", { signal: controller.signal }),
      fetch("/api/dashboard/cards", { signal: controller.signal }),
      fetch("/api/imports/coverage", { signal: controller.signal }),
      fetch("/api/exports/original-activities", { signal: controller.signal }),
      fetch("/api/sync/status", { signal: controller.signal }),
      fetch("/api/sync/plan", { signal: controller.signal }),
      fetch("/api/garmin/connection", { signal: controller.signal }),
    ])
      .then(async ([healthResponse, summaryResponse, weeklyResponse, cardsResponse, coverageResponse, originalsResponse, syncStatusResponse, syncPlanResponse, garminConnectionResponse]) => {
        if (
          !healthResponse.ok ||
          !summaryResponse.ok ||
          !weeklyResponse.ok ||
          !cardsResponse.ok ||
          !coverageResponse.ok ||
          !originalsResponse.ok ||
          !syncStatusResponse.ok ||
          !syncPlanResponse.ok ||
          !garminConnectionResponse.ok
        ) {
          throw new Error("Backend is unavailable");
        }
        const [health, summary, weeklyCalories, dashboardCards, coverage, originalActivities, syncStatus, syncPlan, garminConnection] = await Promise.all([
          healthResponse.json() as Promise<HealthResponse>,
          summaryResponse.json() as Promise<HistorySummary>,
          weeklyResponse.json() as Promise<WeeklyCalories | null>,
          cardsResponse.json() as Promise<DashboardCardLayout[]>,
          coverageResponse.json() as Promise<ImportCoverage>,
          originalsResponse.json() as Promise<OriginalActivityInventory>,
          syncStatusResponse.json() as Promise<SyncStatus>,
          syncPlanResponse.json() as Promise<SyncPlan>,
          garminConnectionResponse.json() as Promise<GarminConnection>,
        ]);
        setConnection({
          kind: "ready",
          health,
          summary,
          weeklyCalories,
          dashboardCards,
          coverage,
          originalActivities,
          syncStatus,
          syncPlan,
          garminConnection,
        });
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
      timezone: browserTimeZone,
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
  const dashboardCards =
    connection.kind === "ready" ? connection.dashboardCards : [];
  const coverage = connection.kind === "ready" ? connection.coverage : null;
  const originalActivities =
    connection.kind === "ready" ? connection.originalActivities : null;
  const syncStatusValue = connection.kind === "ready" ? connection.syncStatus : null;
  const syncPlanValue = connection.kind === "ready" ? connection.syncPlan : null;
  const garminConnectionValue =
    connection.kind === "ready" ? connection.garminConnection : null;
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
      const response = await fetch(
        `/api/activities/${encodeURIComponent(activityId)}?timezone=${encodeURIComponent(browserTimeZone)}`,
      );
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
      return payload.detail ?? "The local request failed.";
    } catch {
      return "The local request failed.";
    }
  };

  const saveDashboardCards = async (nextCards: DashboardCardLayout[]) => {
    if (connection.kind !== "ready") return;
    setIsSavingCards(true);
    setCardLayoutError(null);
    try {
      const response = await fetch("/api/dashboard/cards", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          cards: nextCards.map(({ id, position, is_visible }) => ({
            id,
            position,
            is_visible,
          })),
        }),
      });
      if (!response.ok) throw new Error("The dashboard layout could not be saved.");
      const savedCards = (await response.json()) as DashboardCardLayout[];
      setConnection((current) =>
        current.kind === "ready"
          ? { ...current, dashboardCards: savedCards }
          : current,
      );
    } catch (error: unknown) {
      setCardLayoutError(
        error instanceof Error ? error.message : "The dashboard layout could not be saved.",
      );
    } finally {
      setIsSavingCards(false);
    }
  };

  const setCardVisibility = (id: DashboardCardId, isVisible: boolean) => {
    void saveDashboardCards(
      dashboardCards.map((card) =>
        card.id === id ? { ...card, is_visible: isVisible } : card,
      ),
    );
  };

  const moveCard = (id: DashboardCardId, direction: -1 | 1) => {
    const currentIndex = dashboardCards.findIndex((card) => card.id === id);
    const targetIndex = currentIndex + direction;
    if (currentIndex < 0 || targetIndex < 0 || targetIndex >= dashboardCards.length) return;

    const reordered = [...dashboardCards];
    [reordered[currentIndex], reordered[targetIndex]] = [
      reordered[targetIndex],
      reordered[currentIndex],
    ];
    void saveDashboardCards(
      reordered.map((card, position) => ({ ...card, position })),
    );
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
        fetch(`/api/history/summary?timezone=${encodeURIComponent(browserTimeZone)}`),
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

  const exportRange = new URLSearchParams();
  if (activityRange.start) exportRange.set("start_date", activityRange.start);
  if (activityRange.end) exportRange.set("end_date", activityRange.end);
  const exportQuery = exportRange.toString() ? `?${exportRange.toString()}` : "";

  const previewBackupRestore = async (file: File | null) => {
    if (!file) return;
    setRestoreState({ kind: "loading", filename: file.name });
    try {
      const response = await fetch("/api/restores/preview", {
        method: "POST",
        headers: { "Content-Type": file.type || "application/zip" },
        body: file,
      });
      if (!response.ok) throw new Error(await readError(response));
      const preview = (await response.json()) as RestorePreview;
      setRestoreState({ kind: "ready", filename: file.name, preview });
    } catch (error: unknown) {
      setRestoreState({
        kind: "error",
        message: error instanceof Error ? error.message : "Restore preview failed.",
      });
    }
  };

  const refreshGarminConnection = async () => {
    const [connectionResponse, statusResponse, planResponse] = await Promise.all([
      fetch("/api/garmin/connection"),
      fetch("/api/sync/status"),
      fetch("/api/sync/plan"),
    ]);
    if (!connectionResponse.ok || !statusResponse.ok || !planResponse.ok) return;
    const [garminConnection, refreshedStatus, refreshedPlan] = await Promise.all([
      connectionResponse.json() as Promise<GarminConnection>,
      statusResponse.json() as Promise<SyncStatus>,
      planResponse.json() as Promise<SyncPlan>,
    ]);
    setConnection((current) =>
      current.kind === "ready"
        ? {
            ...current,
            garminConnection,
            syncStatus: refreshedStatus,
            syncPlan: refreshedPlan,
          }
        : current,
    );
  };

  const connectGarmin = async () => {
    setIsConnectingGarmin(true);
    setConnectionMessage(null);
    try {
      const response = await fetch("/api/garmin/connection/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email: garminEmail, password: garminPassword }),
      });
      setGarminPassword("");
      if (!response.ok) throw new Error(await readError(response));
      const result = (await response.json()) as { status: string; message: string };
      setConnectionMessage(result.message);
      await refreshGarminConnection();
    } catch (error: unknown) {
      setGarminPassword("");
      setConnectionMessage(
        error instanceof Error ? error.message : "Garmin sign-in failed.",
      );
    } finally {
      setIsConnectingGarmin(false);
    }
  };

  const submitGarminMfa = async () => {
    setIsConnectingGarmin(true);
    setConnectionMessage(null);
    try {
      const response = await fetch("/api/garmin/connection/mfa", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ code: garminMfaCode }),
      });
      setGarminMfaCode("");
      if (!response.ok) throw new Error(await readError(response));
      const result = (await response.json()) as { message: string };
      setConnectionMessage(result.message);
      await refreshGarminConnection();
    } catch (error: unknown) {
      setGarminMfaCode("");
      setConnectionMessage(
        error instanceof Error ? error.message : "Garmin verification failed.",
      );
    } finally {
      setIsConnectingGarmin(false);
    }
  };

  const probeGarmin = async () => {
    setIsConnectingGarmin(true);
    setConnectionMessage(null);
    try {
      const response = await fetch("/api/garmin/connection/probe", { method: "POST" });
      if (!response.ok) throw new Error(await readError(response));
      const result = (await response.json()) as {
        summary_available: boolean;
        summary_fields: number;
        activities_today: number;
      };
      setConnectionMessage(
        `Read-only check passed: ${result.summary_fields} daily-summary fields and ${result.activities_today} activities today.`,
      );
      await refreshGarminConnection();
    } catch (error: unknown) {
      setConnectionMessage(
        error instanceof Error ? error.message : "Garmin read-only check failed.",
      );
      await refreshGarminConnection();
    } finally {
      setIsConnectingGarmin(false);
    }
  };

  const disconnectGarmin = async () => {
    setIsConnectingGarmin(true);
    try {
      const response = await fetch("/api/garmin/connection", { method: "DELETE" });
      if (!response.ok) throw new Error(await readError(response));
      setConnectionMessage("Saved Garmin session removed.");
      await refreshGarminConnection();
    } catch (error: unknown) {
      setConnectionMessage(
        error instanceof Error ? error.message : "Garmin sign-out failed.",
      );
    } finally {
      setIsConnectingGarmin(false);
    }
  };

  const runSyncNow = async () => {
    setIsSyncing(true);
    setSyncMessage(null);
    try {
      const response = await fetch("/api/sync/run", { method: "POST" });
      if (!response.ok) throw new Error(await readError(response));
      const [statusResponse, planResponse] = await Promise.all([
        fetch("/api/sync/status"),
        fetch("/api/sync/plan"),
      ]);
      if (statusResponse.ok && planResponse.ok) {
        const [refreshedStatus, refreshedPlan] = await Promise.all([
          statusResponse.json() as Promise<SyncStatus>,
          planResponse.json() as Promise<SyncPlan>,
        ]);
        setConnection((current) =>
          current.kind === "ready"
            ? { ...current, syncStatus: refreshedStatus, syncPlan: refreshedPlan }
            : current,
        );
      }
      setSyncMessage("Synchronization completed and checkpoints were refreshed.");
    } catch (error: unknown) {
      setSyncMessage(
        error instanceof Error ? error.message : "Synchronization could not start.",
      );
    } finally {
      setIsSyncing(false);
    }
  };
  const cardRegistry: Record<DashboardCardId, PreviewCard> = {
    latest_steps: {
      id: "latest_steps",
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
    last_activity: {
      id: "last_activity",
      label: "Last activity",
      value: summary?.latest_activity?.name ?? "—",
      detail: summary?.latest_activity
        ? summary.latest_activity.activity_type.replaceAll("_", " ")
        : "No activities loaded",
      subdetail: summary?.latest_activity
        ? `${sourceLabel(summary.latest_activity.source_name)} · ${formatLongDate(summary.latest_activity.local_date)} · ${summary.latest_activity.timezone_used ?? "timezone unavailable"}`
        : undefined,
      tooltip: "The most recently started activity, dated in the browser's local timezone.",
    },
    weekly_calories: {
      id: "weekly_calories",
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
  };
  const previewCards = dashboardCards
    .filter((card) => card.is_visible)
    .map((card) => cardRegistry[card.id]);

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

      <section className="sync" aria-labelledby="sync-title">
        <div className="section-heading sync-heading">
          <div>
            <p>Garmin synchronization</p>
            <h2 id="sync-title">Catch up every missing day</h2>
          </div>
          <button type="button" onClick={() => void runSyncNow()} disabled={isSyncing}>
            {isSyncing ? "Starting…" : "Sync now"}
          </button>
        </div>
        <div className="sync-status-grid">
          <div>
            <span>Connection</span>
            <strong>
              {garminConnectionValue?.status === "connected"
                ? "Connected"
                : garminConnectionValue?.status === "mfa_required"
                  ? "Verification required"
                  : garminConnectionValue?.status === "reconnect_required"
                  ? "Reconnect required"
                  : "Not connected yet"}
            </strong>
          </div>
          <div>
            <span>Catch-up plan</span>
            <strong>
              {syncPlanValue
                ? `${syncPlanValue.total_intervals.toLocaleString()} daily checks`
                : "Loading…"}
            </strong>
          </div>
          <div>
            <span>Late-data overlap</span>
            <strong>{syncStatusValue ? `${syncStatusValue.overlap_days} days` : "—"}</strong>
          </div>
          <div>
            <span>Schedule</span>
            <strong>Open app only</strong>
          </div>
        </div>
        {(garminConnectionValue?.status === "not_connected" ||
          garminConnectionValue?.status === "reconnect_required") && (
          <form
            className="garmin-login"
            onSubmit={(event) => {
              event.preventDefault();
              void connectGarmin();
            }}
          >
            <div>
              <strong>Private Garmin sign-in</strong>
              <span>Credentials go directly to the localhost backend and are not saved.</span>
            </div>
            <label>
              <span>Email</span>
              <input
                type="email"
                autoComplete="username"
                value={garminEmail}
                onChange={(event) => setGarminEmail(event.target.value)}
                required
              />
            </label>
            <label>
              <span>Password</span>
              <input
                type="password"
                autoComplete="current-password"
                value={garminPassword}
                onChange={(event) => setGarminPassword(event.target.value)}
                required
              />
            </label>
            <button type="submit" disabled={isConnectingGarmin}>
              {isConnectingGarmin ? "Connecting…" : "Connect Garmin"}
            </button>
          </form>
        )}
        {garminConnectionValue?.status === "mfa_required" && (
          <form
            className="garmin-login garmin-mfa"
            onSubmit={(event) => {
              event.preventDefault();
              void submitGarminMfa();
            }}
          >
            <div>
              <strong>Garmin verification required</strong>
              <span>Enter the one-time code Garmin sent you.</span>
            </div>
            <label>
              <span>Verification code</span>
              <input
                type="text"
                inputMode="numeric"
                autoComplete="one-time-code"
                value={garminMfaCode}
                onChange={(event) => setGarminMfaCode(event.target.value)}
                required
              />
            </label>
            <button type="submit" disabled={isConnectingGarmin}>
              {isConnectingGarmin ? "Verifying…" : "Verify code"}
            </button>
          </form>
        )}
        {garminConnectionValue?.status === "connected" && (
          <div className="garmin-connected-actions">
            <span>Saved session is available locally.</span>
            <button type="button" onClick={() => void probeGarmin()} disabled={isConnectingGarmin}>
              Run read-only check
            </button>
            <button className="secondary-action" type="button" onClick={() => void disconnectGarmin()} disabled={isConnectingGarmin}>
              Sign out
            </button>
          </div>
        )}
        <div className="sync-checkpoints">
          {syncStatusValue?.checkpoints.map((checkpoint) => (
            <div key={checkpoint.data_type}>
              <span>{checkpoint.data_type.replaceAll("_", " ")}</span>
              <strong>
                {checkpoint.coverage_end
                  ? `Imported through ${formatLongDate(checkpoint.coverage_end)}`
                  : "No imported coverage"}
              </strong>
              <small>
                {checkpoint.last_success_at
                  ? `Last online success ${formatLongDate(checkpoint.last_success_at)}`
                  : "Online verification pending"}
              </small>
            </div>
          ))}
        </div>
        {syncStatusValue?.last_job && (
          <div className={`sync-last-job sync-last-job--${syncStatusValue.last_job.status}`}>
            <strong>Last sync: {syncStatusValue.last_job.status}</strong>
            <span>
              {syncStatusValue.last_job.progress_current.toLocaleString()} of {syncStatusValue.last_job.progress_total?.toLocaleString() ?? "—"} intervals
              {syncStatusValue.last_job.checkpoint?.totals
                ? ` · ${syncStatusValue.last_job.checkpoint.totals.created.toLocaleString()} new · ${syncStatusValue.last_job.checkpoint.totals.updated.toLocaleString()} updated · ${syncStatusValue.last_job.checkpoint.totals.unchanged.toLocaleString()} unchanged`
                : ""}
            </span>
            {syncStatusValue.last_job.error_message && <small>{syncStatusValue.last_job.error_message}</small>}
          </div>
        )}
        <p className="sync-note">
          The catch-up engine, independent checkpoints, retries, and historical reconciliation are ready.
          Private Garmin sign-in is still required before network synchronization can run.
        </p>
        {syncMessage && <p className="sync-message" role="status">{syncMessage}</p>}
        {connectionMessage && <p className="sync-message" role="status">{connectionMessage}</p>}
      </section>

      <section className="preview" aria-labelledby="preview-title">
        <div className="section-heading">
          <div>
            <p>Data preview</p>
            <h2 id="preview-title">A safe dataset to build on</h2>
          </div>
          <div className="preview-actions">
            {dataModeLabel && <div className="synthetic-label">{dataModeLabel}</div>}
            <button
              className="customize-button"
              type="button"
              aria-expanded={isCustomizingCards}
              onClick={() => setIsCustomizingCards((current) => !current)}
            >
              {isCustomizingCards ? "Done" : "Customize cards"}
            </button>
          </div>
        </div>
        {isCustomizingCards && (
          <div className="card-editor">
            <div className="card-editor-heading">
              <div>
                <strong>Dashboard cards</strong>
                <span>Reorder, hide, or restore cards. Changes save locally.</span>
              </div>
              {isSavingCards && <span>Saving…</span>}
            </div>
            <div className="card-editor-list">
              {dashboardCards.map((card, index) => (
                <div className="card-editor-row" key={card.id}>
                  <span className="card-drag-index">{index + 1}</span>
                  <strong>{card.label}</strong>
                  <div className="card-editor-controls">
                    <button
                      type="button"
                      aria-label={`Move ${card.label} up`}
                      disabled={isSavingCards || index === 0}
                      onClick={() => moveCard(card.id, -1)}
                    >
                      ↑
                    </button>
                    <button
                      type="button"
                      aria-label={`Move ${card.label} down`}
                      disabled={isSavingCards || index === dashboardCards.length - 1}
                      onClick={() => moveCard(card.id, 1)}
                    >
                      ↓
                    </button>
                    <button
                      className={card.is_visible ? "card-remove" : "card-add"}
                      type="button"
                      disabled={isSavingCards}
                      onClick={() => setCardVisibility(card.id, !card.is_visible)}
                    >
                      {card.is_visible ? "Hide" : "Add"}
                    </button>
                  </div>
                </div>
              ))}
            </div>
            {cardLayoutError && (
              <p className="card-editor-error" role="alert">{cardLayoutError}</p>
            )}
          </div>
        )}
        {connection.kind === "checking" && (
          <p className="empty-cards">Loading dashboard cards…</p>
        )}
        {connection.kind === "ready" && previewCards.length === 0 && (
          <p className="empty-cards">No cards are visible. Use Customize cards to add one.</p>
        )}
        <div className={`preview-grid preview-grid--${previewCards.length}`}>
          {previewCards.map((card) => (
            <article className="data-card" key={card.id}>
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
            <span className="timezone-label">Calendar dates shown in {browserTimeZone}</span>
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
                    <span className="activity-date">{formatLongDate(activity.local_date)}</span>
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

      <section className="exports" aria-labelledby="exports-title">
        <div className="section-heading">
          <div>
            <p>Import / Export</p>
            <h2 id="exports-title">Keep a portable copy</h2>
          </div>
          <span className="export-range-label">
            {activityRange.start && activityRange.end
              ? `${formatLongDate(activityRange.start)} – ${formatLongDate(activityRange.end)}`
              : "All dates"}
          </span>
        </div>
        <p className="export-copy">
          CSV and JSON use the activity date range selected above. Exports are generated
          locally and never contain credentials or session tokens.
        </p>
        <div className="export-grid">
          <article className="export-panel">
            <span>Portable data</span>
            <h3>Spreadsheet and JSON</h3>
            <p>Download normalized app records with stable identifiers, units, and timestamps.</p>
            <div className="export-actions">
              <a href={`/api/exports/csv/activities${exportQuery}`} download>Activities CSV</a>
              <a href={`/api/exports/csv/metrics${exportQuery}`} download>Health metrics CSV</a>
              <a href={`/api/exports/csv/training${exportQuery}`} download>Training CSV</a>
              <a href={`/api/exports/csv/nutrition${exportQuery}`} download>Nutrition CSV</a>
              <a href={`/api/exports/data.json${exportQuery}`} download>Versioned JSON</a>
            </div>
          </article>
          <article className="export-panel">
            <span>Full backup</span>
            <h3>Database snapshot</h3>
            <p>Includes relationships, settings, and every completed module in one validated ZIP.</p>
            <label className="backup-option">
              <input
                type="checkbox"
                checked={includeOriginalsInBackup}
                onChange={(event) => setIncludeOriginalsInBackup(event.target.checked)}
              />
              Include original source archives
            </label>
            <small>
              {includeOriginalsInBackup
                ? "This can make the backup very large and includes private Garmin source data."
                : "Original private archives stay excluded; credentials are always excluded."}
            </small>
            <a
              className="primary-export-action"
              href={`/api/exports/backup.zip?include_originals=${includeOriginalsInBackup}`}
              download
            >
              Download backup ZIP
            </a>
          </article>
          <article className="export-panel">
            <span>Preserved originals</span>
            <h3>Activity source files</h3>
            <p>
              {originalActivities?.available
                ? `${originalActivities.files.toLocaleString()} original FIT/TCX/GPX files are available as preserved source bytes.`
                : "No preserved original activity files are available."}
            </p>
            {originalActivities?.available && (
              <a className="primary-export-action" href="/api/exports/original-activities.zip" download>
                Download originals ZIP
              </a>
            )}
          </article>
          <article className="export-panel">
            <span>Restore safety check</span>
            <h3>Preview before restoring</h3>
            <p>Checks paths, checksum, schema, database integrity, and relationships without changing data.</p>
            <label className="restore-picker">
              <span>{restoreState.kind === "loading" ? "Checking backup…" : "Choose backup ZIP"}</span>
              <input
                type="file"
                accept=".zip,application/zip"
                disabled={restoreState.kind === "loading"}
                onChange={(event) => void previewBackupRestore(event.target.files?.[0] ?? null)}
              />
            </label>
            {restoreState.kind === "ready" && (
              <p className="restore-result restore-result--ready" role="status">
                Preview passed for {restoreState.filename}. {Object.values(restoreState.preview.table_counts).reduce((sum, count) => sum + count, 0).toLocaleString()} records checked. No data changed.
              </p>
            )}
            {restoreState.kind === "error" && (
              <p className="restore-result restore-result--error" role="alert">{restoreState.message}</p>
            )}
          </article>
        </div>
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
