import { useEffect, useRef, useState } from "react";
import MaintenancePanel, { type MaintenanceResult } from "./MaintenancePanel";

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
      totals?: { created: number; updated: number; unchanged: number; received: number; detail_samples?: number };
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

type UserProfile = {
  display_name: string | null;
  timezone: string | null;
  preferred_distance_unit: "km" | "mi";
  preferred_weight_unit: "kg" | "lb";
  birth_date: string | null;
  sex: string | null;
  height_cm: number | null;
  weight_kg: number | null;
  updated_at: string | null;
};

type UserGoal = {
  id: string | null;
  goal_type: string;
  title: string;
  target_value: number | null;
  target_unit: string | null;
  target_date: string | null;
  status: "active" | "paused" | "achieved";
  notes: string | null;
};

type AiProviderName = "ollama" | "openai";

type AiSettings = {
  active_provider: AiProviderName;
  ollama_model: string;
  openai_model: string;
  updated_at: string;
};

type AiProviderStatus = {
  active_provider: AiProviderName;
  providers: Record<AiProviderName, {
    configured: boolean;
    available: boolean;
    model: string;
    detail: string;
  }>;
};

type SettingsProposal = {
  id: string;
  target: "profile" | "goals";
  before: Record<string, unknown> | Array<Record<string, unknown>>;
  after: Record<string, unknown> | Array<Record<string, unknown>>;
  status: "pending" | "saved";
};

function proposalRows(proposal: SettingsProposal) {
  const before = Array.isArray(proposal.before) ? proposal.before : [proposal.before];
  const after = Array.isArray(proposal.after) ? proposal.after : [proposal.after];
  return after.flatMap((item, index) => {
    const old = proposal.target === "goals" ? before.find((entry) => entry.id === item.id) ?? {} : before[index] ?? {};
    return Object.keys(item).filter((key) => key !== "id" && (item[key] ?? null) !== (old[key] ?? null)).map((key) => ({
      label: key.replaceAll("_", " "),
      before: old[key] == null ? "Not set" : String(old[key]),
      after: item[key] == null ? "Not set" : String(item[key]),
    }));
  });
}

type ChatEvidence = {
  maintenance?: MaintenanceResult;
  proposal?: SettingsProposal;
  tool: string;
  period?: { start: string; end: string };
  period_a?: { start: string; end: string };
  period_b?: { start: string; end: string };
  freshness?: {
    latest_recorded_at?: string | null;
    latest_started_at?: string | null;
    sources?: string[];
  };
  record_count?: number;
  total_matches?: number;
  returned_count?: number;
  candidate_pool_count?: number;
  evaluated_count?: number;
  truncated?: boolean;
  missing_metric_types?: string[];
  unavailable_criteria?: string[];
  criteria?: Array<{
    field: string;
    label: string;
    unit?: string;
    applied: boolean;
    reference_value?: string | number;
    accepted_values?: string[];
    tolerance_percent?: number;
    minimum?: number;
    maximum?: number;
    reason?: string;
    description?: string;
  }>;
  reference_record?: {
    id: string;
    name?: string;
    activity_type: string;
    local_date: string;
    url: string;
  };
  records?: Array<{
    id: string;
    name?: string;
    activity_type: string;
    local_date: string;
    similarity_score?: number;
    route_overlap_percent?: number;
    direction?: string;
    endpoint_distance_meters?: number;
    url: string;
  }>;
  course_progress?: null | {
    attempt_count: number;
    earliest: { id: string; local_date: string; evidence_url: string };
    latest: { id: string; local_date: string; evidence_url: string };
    changes_latest_minus_earliest: Array<{
      metric: string;
      unit: string;
      earliest: number;
      latest: number;
      absolute: number;
      percent: number | null;
    }>;
    interpretation_notes: string[];
  };
  privacy?: string;
  limitations?: string[];
};

type ChatMessage = {
  id: string;
  role: "user" | "assistant";
  content: string;
  evidence: ChatEvidence[];
};

type ChatStreamEvent =
  | { type: "start"; provider: AiProviderName; model: string }
  | { type: "tool"; evidence: ChatEvidence }
  | { type: "delta"; text: string }
  | { type: "complete"; provider: AiProviderName; model: string; evidence: ChatEvidence[] }
  | { type: "error"; message: string };

type AppSettings = {
  profile: UserProfile;
  goals: UserGoal[];
  ai: AiSettings;
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
      settings: AppSettings;
      aiProviderStatus: AiProviderStatus;
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

const todayInBrowserTimeZone = () => {
  const parts = new Intl.DateTimeFormat("en-US", {
    timeZone: browserTimeZone,
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).formatToParts(new Date());
  const value = Object.fromEntries(parts.map((part) => [part.type, part.value]));
  return `${value.year}-${value.month}-${value.day}`;
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

const formatDistance = (meters: number, unit: "km" | "mi") =>
  unit === "mi"
    ? `${(meters / 1609.344).toFixed(1)} mi`
    : `${(meters / 1000).toFixed(1)} km`;

const formatSpeed = (metersPerSecond: number, unit: "km" | "mi") =>
  unit === "mi"
    ? `${(metersPerSecond * 2.236936).toFixed(1)} mph`
    : `${(metersPerSecond * 3.6).toFixed(1)} km/h`;

const formatSimilarityCriterion = (
  criterion: NonNullable<ChatEvidence["criteria"]>[number],
  distanceUnit: "km" | "mi",
) => {
  if (!criterion.applied) return `${criterion.label}: ${criterion.reason ?? "not applied"}`;
  if (criterion.description) return `${criterion.label}: ${criterion.description}`;
  if (criterion.field === "activity_type") {
    return `${criterion.label}: ${(criterion.accepted_values ?? []).map((value) => value.replaceAll("_", " ")).join(", ")}`;
  }
  const tolerance = typeof criterion.tolerance_percent === "number"
    ? ` (±${criterion.tolerance_percent}%)`
    : "";
  if (criterion.minimum === undefined || criterion.maximum === undefined) {
    return criterion.label;
  }
  if (criterion.unit === "seconds") {
    return `${criterion.label}: ${formatDuration(criterion.minimum)}–${formatDuration(criterion.maximum)}${tolerance}`;
  }
  if (criterion.unit === "hours") {
    return `${criterion.label}: ${criterion.minimum.toFixed(1)}–${criterion.maximum.toFixed(1)} hours${tolerance}`;
  }
  if (criterion.unit === "kilometers") {
    const minimumMeters = criterion.minimum * 1_000;
    const maximumMeters = criterion.maximum * 1_000;
    return `${criterion.label}: ${formatDistance(minimumMeters, distanceUnit)}–${formatDistance(maximumMeters, distanceUnit)}${tolerance}`;
  }
  if (criterion.field === "distance_meters") {
    return `${criterion.label}: ${formatDistance(criterion.minimum, distanceUnit)}–${formatDistance(criterion.maximum, distanceUnit)}${tolerance}`;
  }
  return `${criterion.label}: ${Math.round(criterion.minimum).toLocaleString()}–${Math.round(criterion.maximum).toLocaleString()} ${criterion.unit ?? ""}${tolerance}`.trim();
};

const formatCourseMetric = (value: number, unit: string) => {
  if (unit === "hours") return `${value.toFixed(2)} h`;
  if (unit === "kilometers_per_hour") return `${value.toFixed(1)} km/h`;
  if (unit === "bpm") return `${Math.round(value)} bpm`;
  if (unit === "watts") return `${Math.round(value)} W`;
  if (unit === "rpm") return `${Math.round(value)} rpm`;
  return value.toFixed(1);
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

function ActivityDetailPanel({
  activity,
  distanceUnit,
}: {
  activity: ActivityDetail;
  distanceUnit: "km" | "mi";
}) {
  const summary = activity.sample_summary;
  const details = [
    ["Duration", formatDuration(activity.duration_seconds)],
    [
      "Distance",
      activity.distance_meters === null
        ? "Not recorded"
        : formatDistance(activity.distance_meters, distanceUnit),
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
        : formatSpeed(summary.maximum_speed_mps, distanceUnit),
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
  const [settingsDraft, setSettingsDraft] = useState<AppSettings | null>(null);
  const [settingsMessage, setSettingsMessage] = useState<string | null>(null);
  const [isSavingSettings, setIsSavingSettings] = useState(false);
  const [chatInput, setChatInput] = useState("");
  const [chatMessages, setChatMessages] = useState<ChatMessage[]>([]);
  const [chatStatus, setChatStatus] = useState<{
    kind: "idle" | "streaming" | "error";
    provider?: AiProviderName;
    model?: string;
    slow?: boolean;
    message?: string;
  }>({ kind: "idle" });
  const [maintenanceVersion, setMaintenanceVersion] = useState(0);
  const [maintenanceActionError, setMaintenanceActionError] = useState<string | null>(null);
  const chatAbortController = useRef<AbortController | null>(null);
  const scheduledSyncInFlight = useRef(false);

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
      fetch("/api/settings", { signal: controller.signal }),
      fetch("/api/ai/providers/status", { signal: controller.signal }),
    ])
      .then(async ([healthResponse, summaryResponse, weeklyResponse, cardsResponse, coverageResponse, originalsResponse, syncStatusResponse, syncPlanResponse, garminConnectionResponse, settingsResponse, aiStatusResponse]) => {
        if (
          !healthResponse.ok ||
          !summaryResponse.ok ||
          !weeklyResponse.ok ||
          !cardsResponse.ok ||
          !coverageResponse.ok ||
          !originalsResponse.ok ||
          !syncStatusResponse.ok ||
          !syncPlanResponse.ok ||
          !garminConnectionResponse.ok ||
          !settingsResponse.ok ||
          !aiStatusResponse.ok
        ) {
          throw new Error("Backend is unavailable");
        }
        const [health, summary, weeklyCalories, dashboardCards, coverage, originalActivities, syncStatus, syncPlan, garminConnection, settings, aiProviderStatus] = await Promise.all([
          healthResponse.json() as Promise<HealthResponse>,
          summaryResponse.json() as Promise<HistorySummary>,
          weeklyResponse.json() as Promise<WeeklyCalories | null>,
          cardsResponse.json() as Promise<DashboardCardLayout[]>,
          coverageResponse.json() as Promise<ImportCoverage>,
          originalsResponse.json() as Promise<OriginalActivityInventory>,
          syncStatusResponse.json() as Promise<SyncStatus>,
          syncPlanResponse.json() as Promise<SyncPlan>,
          garminConnectionResponse.json() as Promise<GarminConnection>,
          settingsResponse.json() as Promise<AppSettings>,
          aiStatusResponse.json() as Promise<AiProviderStatus>,
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
          settings,
          aiProviderStatus,
        });
        setSettingsDraft(settings);
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
  const preferredDistanceUnit = settingsDraft?.profile.preferred_distance_unit ?? "km";
  const activeAiProvider = settingsDraft?.ai.active_provider ?? "ollama";
  const activeAiStatus = connection.kind === "ready"
    ? connection.aiProviderStatus.providers[activeAiProvider]
    : null;
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

  const saveProfileSettings = async () => {
    if (!settingsDraft) return;
    setIsSavingSettings(true);
    setSettingsMessage(null);
    try {
      const response = await fetch("/api/settings/profile", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(settingsDraft.profile),
      });
      if (!response.ok) throw new Error(await readError(response));
      const profile = (await response.json()) as UserProfile;
      setSettingsDraft((current) => current ? { ...current, profile } : current);
      setConnection((current) => current.kind === "ready"
        ? { ...current, settings: { ...current.settings, profile } }
        : current);
      setSettingsMessage("Profile settings saved locally.");
    } catch (error: unknown) {
      setSettingsMessage(error instanceof Error ? error.message : "Profile settings could not be saved.");
    } finally {
      setIsSavingSettings(false);
    }
  };

  const saveGoalSettings = async () => {
    if (!settingsDraft) return;
    setIsSavingSettings(true);
    setSettingsMessage(null);
    try {
      const response = await fetch("/api/settings/goals", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ goals: settingsDraft.goals }),
      });
      if (!response.ok) throw new Error(await readError(response));
      const goals = (await response.json()) as UserGoal[];
      setSettingsDraft((current) => current ? { ...current, goals } : current);
      setConnection((current) => current.kind === "ready"
        ? { ...current, settings: { ...current.settings, goals } }
        : current);
      setSettingsMessage("Training goals saved locally.");
    } catch (error: unknown) {
      setSettingsMessage(error instanceof Error ? error.message : "Training goals could not be saved.");
    } finally {
      setIsSavingSettings(false);
    }
  };

  const saveAISettings = async () => {
    if (!settingsDraft) return;
    setIsSavingSettings(true);
    setSettingsMessage(null);
    try {
      const response = await fetch("/api/settings/ai", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(settingsDraft.ai),
      });
      if (!response.ok) throw new Error(await readError(response));
      const ai = (await response.json()) as AiSettings;
      const statusResponse = await fetch("/api/ai/providers/status");
      if (!statusResponse.ok) throw new Error(await readError(statusResponse));
      const aiProviderStatus = (await statusResponse.json()) as AiProviderStatus;
      setSettingsDraft((current) => current ? { ...current, ai } : current);
      setConnection((current) => current.kind === "ready"
        ? {
            ...current,
            settings: { ...current.settings, ai },
            aiProviderStatus,
          }
        : current);
      setSettingsMessage(`AI provider saved: ${ai.active_provider === "openai" ? "OpenAI" : "Qwen through Ollama"}.`);
    } catch (error: unknown) {
      setSettingsMessage(error instanceof Error ? error.message : "AI settings could not be saved.");
    } finally {
      setIsSavingSettings(false);
    }
  };

  const sendChatMessage = async (suggestedMessage?: string) => {
    const message = (suggestedMessage ?? chatInput).trim();
    if (!message || chatStatus.kind === "streaming") return;

    const userMessage: ChatMessage = {
      id: crypto.randomUUID(),
      role: "user",
      content: message,
      evidence: [],
    };
    const assistantId = crypto.randomUUID();
    const assistantMessage: ChatMessage = {
      id: assistantId,
      role: "assistant",
      content: "",
      evidence: [],
    };
    const history = chatMessages
      .filter((item) => item.content.trim())
      .slice(-20)
      .map(({ role, content }) => ({ role, content }));
    setChatMessages((current) => [...current, userMessage, assistantMessage]);
    setChatInput("");
    setChatStatus({ kind: "streaming", slow: false });

    const controller = new AbortController();
    chatAbortController.current = controller;
    const slowTimer = window.setTimeout(() => {
      setChatStatus((current) => current.kind === "streaming"
        ? { ...current, slow: true }
        : current);
    }, 10_000);

    const applyEvent = (event: ChatStreamEvent) => {
      if (event.type === "start") {
        setChatStatus({
          kind: "streaming",
          provider: event.provider,
          model: event.model,
          slow: false,
        });
      } else if (event.type === "tool") {
        if (event.evidence.maintenance?.saved) setMaintenanceVersion((current) => current + 1);
        setChatMessages((current) => current.map((item) => item.id === assistantId
          ? { ...item, evidence: [...item.evidence, event.evidence] }
          : item));
      } else if (event.type === "delta") {
        setChatMessages((current) => current.map((item) => item.id === assistantId
          ? { ...item, content: item.content + event.text }
          : item));
      } else if (event.type === "complete") {
        setChatStatus({
          kind: "idle",
          provider: event.provider,
          model: event.model,
        });
      } else if (event.type === "error") {
        setChatMessages((current) => current.map((item) => item.id === assistantId
          ? { ...item, content: item.content || event.message }
          : item));
        setChatStatus({ kind: "error", message: event.message });
      }
    };

    try {
      const response = await fetch("/api/ai/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message, history, timezone: browserTimeZone, operation_id: userMessage.id,
          clarification_id: chatMessages.filter((item) => item.role === "assistant").at(-1)?.evidence.find((entry) => entry.maintenance?.clarification_id)?.maintenance?.clarification_id }),
        signal: controller.signal,
      });
      if (!response.ok) throw new Error(await readError(response));
      if (!response.body) throw new Error("The assistant response could not be streamed.");

      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";
      while (true) {
        const { done, value } = await reader.read();
        buffer += decoder.decode(value, { stream: !done });
        const lines = buffer.split("\n");
        buffer = lines.pop() ?? "";
        for (const line of lines) {
          if (line.trim()) applyEvent(JSON.parse(line) as ChatStreamEvent);
        }
        if (done) break;
      }
      if (buffer.trim()) applyEvent(JSON.parse(buffer) as ChatStreamEvent);
      setChatStatus((current) => current.kind === "streaming"
        ? { kind: "idle", provider: current.provider, model: current.model }
        : current);
    } catch (error: unknown) {
      if (error instanceof DOMException && error.name === "AbortError") {
        setChatMessages((current) => current.map((item) => item.id === assistantId
          ? { ...item, content: item.content || "Response stopped." }
          : item));
        setChatStatus({ kind: "idle" });
      } else {
        const messageText = error instanceof Error ? error.message : "The assistant could not respond.";
        setChatMessages((current) => current.map((item) => item.id === assistantId
          ? { ...item, content: item.content || messageText }
          : item));
        setChatStatus({ kind: "error", message: messageText });
      }
    } finally {
      window.clearTimeout(slowTimer);
      chatAbortController.current = null;
    }
  };

  const [savingProposal, setSavingProposal] = useState<string | null>(null);
  const [proposalError, setProposalError] = useState<string | null>(null);
  const saveChatProposal = async (proposal: SettingsProposal) => {
    setSavingProposal(proposal.id);
    setProposalError(null);
    try {
      const response = await fetch(`/api/ai/settings-changes/${encodeURIComponent(proposal.id)}/confirm`, { method: "POST" });
      if (!response.ok) throw new Error(await readError(response));
      const settings = await response.json() as AppSettings;
      setSettingsDraft(settings);
      setConnection((current) => current.kind === "ready" ? { ...current, settings } : current);
      setChatMessages((current) => current.map((item) => ({ ...item,
        content: item.evidence.some((entry) => entry.proposal?.id === proposal.id)
          ? `Your ${proposal.target === "goals" ? "goal" : "profile"} change was saved locally. You can correct it in Settings or ask for another change in chat.`
          : item.content,
        evidence: item.evidence.map((entry) =>
        entry.proposal?.id === proposal.id ? { ...entry, proposal: { ...entry.proposal, status: "saved" } } : entry) })));
    } catch (error) {
      setProposalError(error instanceof Error ? error.message : "The change could not be saved.");
    } finally {
      setSavingProposal(null);
    }
  };

  const undoChatMaintenance = async (result: MaintenanceResult) => {
    if (!result.operation_id) return;
    setMaintenanceActionError(null);
    try {
      const response = await fetch(`/api/maintenance/operations/${encodeURIComponent(result.operation_id)}/undo`, {
        method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ operation_id: `undo-${result.operation_id}` }),
      });
      if (!response.ok) throw new Error(await readError(response));
      const undone = await response.json() as MaintenanceResult;
      setChatMessages((current) => current.map((item) => ({ ...item,
        content: item.evidence.some((entry) => entry.maintenance?.operation_id === result.operation_id) ? "Maintenance action undone locally. Revision history is retained." : item.content,
        evidence: item.evidence.map((entry) => entry.maintenance?.operation_id === result.operation_id
          ? { ...entry, maintenance: { ...undone, undo_available: false } } : entry),
      })));
      setMaintenanceVersion((current) => current + 1);
    } catch (error) { setMaintenanceActionError(error instanceof Error ? error.message : "This action could not be undone."); }
  };

  const stopChatResponse = () => {
    chatAbortController.current?.abort();
  };

  const addGoal = () => {
    setSettingsDraft((current) => current
      ? {
          ...current,
          goals: [
            ...current.goals,
            {
              id: null,
              goal_type: "general",
              title: "",
              target_value: null,
              target_unit: null,
              target_date: null,
              status: "active",
              notes: null,
            },
          ],
        }
      : current);
  };

  const updateGoal = (index: number, update: Partial<UserGoal>) => {
    setSettingsDraft((current) => current
      ? {
          ...current,
          goals: current.goals.map((goal, goalIndex) =>
            goalIndex === index ? { ...goal, ...update } : goal,
          ),
        }
      : current);
  };

  const removeGoal = (index: number) => {
    setSettingsDraft((current) => current
      ? { ...current, goals: current.goals.filter((_, goalIndex) => goalIndex !== index) }
      : current);
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

  const refreshSyncedData = async () => {
    const [summaryResponse, weeklyResponse, statusResponse, planResponse, connectionResponse] =
      await Promise.all([
        fetch(`/api/history/summary?timezone=${encodeURIComponent(browserTimeZone)}`),
        fetch("/api/history/weekly-calories"),
        fetch("/api/sync/status"),
        fetch("/api/sync/plan"),
        fetch("/api/garmin/connection"),
      ]);
    if (
      !summaryResponse.ok ||
      !weeklyResponse.ok ||
      !statusResponse.ok ||
      !planResponse.ok ||
      !connectionResponse.ok
    ) {
      throw new Error("Synced data could not be refreshed.");
    }
    const [refreshedSummary, refreshedWeekly, refreshedStatus, refreshedPlan, garminConnection] =
      await Promise.all([
        summaryResponse.json() as Promise<HistorySummary>,
        weeklyResponse.json() as Promise<WeeklyCalories | null>,
        statusResponse.json() as Promise<SyncStatus>,
        planResponse.json() as Promise<SyncPlan>,
        connectionResponse.json() as Promise<GarminConnection>,
      ]);
    setConnection((current) =>
      current.kind === "ready"
        ? {
            ...current,
            summary: refreshedSummary,
            weeklyCalories: refreshedWeekly,
            syncStatus: refreshedStatus,
            syncPlan: refreshedPlan,
            garminConnection,
          }
        : current,
    );

    if (activityRange.start && activityRange.end && activityRange.start <= activityRange.end) {
      const parameters = new URLSearchParams({
        limit: "50",
        start_date: activityRange.start,
        end_date: activityRange.end,
        timezone: browserTimeZone,
      });
      const activitiesResponse = await fetch(`/api/activities?${parameters.toString()}`);
      if (activitiesResponse.ok) {
        setActivityState({
          kind: "ready",
          items: (await activitiesResponse.json()) as Activity[],
        });
      }
    }
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

  const setDailySync = async (enabled: boolean) => {
    setIsSyncing(true);
    setSyncMessage(null);
    try {
      const response = await fetch("/api/sync/schedule", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ enabled }),
      });
      if (!response.ok) throw new Error(await readError(response));
      const refreshedStatus = (await response.json()) as SyncStatus;
      setConnection((current) =>
        current.kind === "ready"
          ? { ...current, syncStatus: refreshedStatus }
          : current,
      );
      setSyncMessage(
        enabled
          ? "Daily catch-up is enabled while this app is open."
          : "Daily catch-up is paused; Sync now remains available.",
      );
    } catch (error: unknown) {
      setSyncMessage(
        error instanceof Error ? error.message : "The synchronization schedule could not be changed.",
      );
    } finally {
      setIsSyncing(false);
    }
  };

  const runSyncNow = async () => {
    setIsSyncing(true);
    setSyncMessage(null);
    try {
      const response = await fetch("/api/sync/run", { method: "POST" });
      if (!response.ok) throw new Error(await readError(response));
      const result = (await response.json()) as {
        totals: { created: number; updated: number; unchanged: number; received: number; detail_samples?: number };
      };
      await refreshSyncedData();
      setSyncMessage(
        `Synchronization completed: ${result.totals.created.toLocaleString()} new, ${result.totals.updated.toLocaleString()} updated, ${result.totals.unchanged.toLocaleString()} unchanged, and ${(result.totals.detail_samples ?? 0).toLocaleString()} sensor samples imported.`,
      );
    } catch (error: unknown) {
      setSyncMessage(
        error instanceof Error ? error.message : "Synchronization could not start.",
      );
    } finally {
      setIsSyncing(false);
    }
  };

  useEffect(() => {
    if (
      !syncStatusValue?.schedule_enabled ||
      garminConnectionValue?.status !== "connected"
    ) {
      return;
    }
    let cancelled = false;
    const checkScheduledSync = async () => {
      if (scheduledSyncInFlight.current) return;
      scheduledSyncInFlight.current = true;
      try {
        const response = await fetch(
          `/api/sync/scheduled?through_date=${todayInBrowserTimeZone()}`,
          { method: "POST" },
        );
        if (!response.ok) throw new Error(await readError(response));
        const result = (await response.json()) as {
          status: "completed" | "skipped";
          reason?: string;
          totals?: { created: number; updated: number; unchanged: number; received: number; detail_samples?: number };
        };
        if (!cancelled && result.status === "completed") {
          await refreshSyncedData();
          setSyncMessage(
            `Daily catch-up completed: ${result.totals?.created ?? 0} new, ${result.totals?.updated ?? 0} updated, and ${result.totals?.detail_samples ?? 0} sensor samples imported.`,
          );
        }
      } catch (error: unknown) {
        if (!cancelled) {
          setSyncMessage(
            error instanceof Error ? error.message : "Automatic catch-up could not run.",
          );
          await refreshGarminConnection();
        }
      } finally {
        scheduledSyncInFlight.current = false;
      }
    };
    const initialCheck = window.setTimeout(() => void checkScheduledSync(), 0);
    const interval = window.setInterval(() => void checkScheduledSync(), 15 * 60 * 1000);
    return () => {
      cancelled = true;
      window.clearTimeout(initialCheck);
      window.clearInterval(interval);
    };
  }, [syncStatusValue?.schedule_enabled, garminConnectionValue?.status]);

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
      <nav className="app-navigation" aria-label="Main navigation">
        <a href="#dashboard">Dashboard</a>
        <a href="#activities">Activities</a>
        <a href="#sync">Sync</a>
        <a href="#assistant">Assistant</a>
        <a href="#maintenance">Maintenance</a>
        <a href="#data">Data</a>
        <a href="#settings">Settings</a>
      </nav>
      <header className="hero" id="dashboard">
        <p className="eyebrow">Personal health workspace</p>
        <h1>Your training history,<br />kept close.</h1>
        <p className="intro">
          Your imported history and live Garmin updates stay on this computer
          while normalized records power the dashboard and grounded assistant.
        </p>
        <div className={`connection connection--${connection.kind}`}>
          <span aria-hidden="true" />
          {statusText}
        </div>
      </header>

      <section className="sync" id="sync" aria-labelledby="sync-title">
        <div className="section-heading sync-heading">
          <div>
            <p>Garmin synchronization</p>
            <h2 id="sync-title">Catch up every missing day</h2>
          </div>
          <button
            type="button"
            onClick={() => void runSyncNow()}
            disabled={isSyncing || garminConnectionValue?.status !== "connected"}
          >
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
            <strong>
              {syncStatusValue?.schedule_enabled ? "Daily · app open" : "Off · app open only"}
            </strong>
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
            <button
              className="secondary-action"
              type="button"
              onClick={() => void setDailySync(!syncStatusValue?.schedule_enabled)}
              disabled={isSyncing}
            >
              {syncStatusValue?.schedule_enabled ? "Pause daily sync" : "Enable daily sync"}
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
                ? ` · ${syncStatusValue.last_job.checkpoint.totals.created.toLocaleString()} new · ${syncStatusValue.last_job.checkpoint.totals.updated.toLocaleString()} updated · ${syncStatusValue.last_job.checkpoint.totals.unchanged.toLocaleString()} unchanged · ${(syncStatusValue.last_job.checkpoint.totals.detail_samples ?? 0).toLocaleString()} sensor samples`
                : ""}
            </span>
            {syncStatusValue.last_job.error_message && <small>{syncStatusValue.last_job.error_message}</small>}
          </div>
        )}
        <p className="sync-note">
          {garminConnectionValue?.status === "connected"
            ? `Every run catches up all missing dates and rechecks the latest ${syncStatusValue?.overlap_days ?? 3} days. Daily sync runs only while this app is open.`
            : "Private Garmin sign-in is required before synchronization can run."}
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

      <section className="activities" id="activities" aria-labelledby="activities-title">
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
                  : formatDistance(activity.distance_meters, preferredDistanceUnit),
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
                    <ActivityDetailPanel
                      activity={activityDetail.activity}
                      distanceUnit={preferredDistanceUnit}
                    />
                  )}
                </article>
              );
            })}
          </div>
        )}
      </section>

      <section className="assistant" id="assistant" aria-labelledby="assistant-title">
        <div className="section-heading assistant-heading">
          <div>
            <p>Grounded history assistant</p>
            <h2 id="assistant-title">Ask your Garmin data</h2>
          </div>
          <div className={`assistant-provider ${activeAiStatus?.available ? "assistant-provider--ready" : "assistant-provider--attention"}`}>
            <strong>{activeAiProvider === "openai" ? "OpenAI" : "Qwen / Ollama"}</strong>
            <span>{activeAiStatus?.available ? "Ready" : "Setup needed"}</span>
          </div>
        </div>
        <p className="assistant-intro">
          Explore history, compare rides, and assess a ride against its session intent.
          Calculations use recorded data. You can also ask to update your profile
          or goals; review the proposed changes and save them here. Goals are optional.
        </p>
        <p className="assistant-privacy">
          {activeAiProvider === "openai"
            ? "OpenAI mode sends your question, recent chat context, and only the relevant tool results to the OpenAI API."
            : "Qwen mode sends the conversation and tool results only to Ollama on this computer."}
          {" "}Chat messages are currently kept only in this page session.
        </p>

        {proposalError && <p role="alert">{proposalError}</p>}
        {maintenanceActionError && <p role="alert">{maintenanceActionError}</p>}
        <div className="chat-shell">
          {chatMessages.length === 0 ? (
            <div className="chat-empty">
              <strong>Try a grounded question</strong>
              <div className="chat-suggestions">
                <button type="button" onClick={() => void sendChatMessage("Summarize my steps and sleep over the last seven days.")}>Last seven days</button>
                <button type="button" onClick={() => void sendChatMessage("Compare my running volume over the last two four-week periods.")}>Compare running</button>
                <button type="button" onClick={() => void sendChatMessage("Find rides similar to my latest ride and explain the matching criteria.")}>Similar rides</button>
                <button type="button" onClick={() => void sendChatMessage("Find earlier rides on the same GPS course as my latest ride and show how my performance changed.")}>Same course</button>
                <button type="button" onClick={() => void sendChatMessage("Was my latest ride effective? In what way?")}>Ride effectiveness</button>
                <button type="button" onClick={() => void sendChatMessage("When did I last replace the rear tire on my road bike?")}>Maintenance history</button>
                <button type="button" onClick={() => void sendChatMessage("Set my goal to improve cycling endurance.")}>Set a goal</button>
                <button type="button" onClick={() => void sendChatMessage("List my three most recent activities and the heart-rate or power data available for each.")}>Recent activities</button>
              </div>
            </div>
          ) : (
            <div className="chat-messages" aria-live="polite">
              {chatMessages.map((message) => (
                <article className={`chat-message chat-message--${message.role}`} key={message.id}>
                  <span>{message.role === "user" ? "You" : "Assistant"}</span>
                  <p>{message.content || (chatStatus.kind === "streaming" ? "Checking your records…" : "No response was returned.")}</p>
                  {message.evidence.length > 0 && (
                    <div className="chat-evidence">
                      {message.evidence.map((evidence, index) => (
                        <div key={`${message.id}-${evidence.tool}-${index}`}>
                          <strong>{evidence.maintenance ? "Maintenance history" : evidence.tool === "propose_settings_change" ? "Settings change" : evidence.tool === "assess_ride" ? "Ride assessment" : evidence.tool === "running_volume_trend" ? "Weekly running volume" : evidence.tool.replaceAll("_", " ")}</strong>
                          {evidence.period && <span>{formatLongDate(evidence.period.start)} – {formatLongDate(evidence.period.end)}</span>}
                          {evidence.period_a && evidence.period_b && (
                            <span>
                              {formatLongDate(evidence.period_a.start)}–{formatLongDate(evidence.period_a.end)} vs. {formatLongDate(evidence.period_b.start)}–{formatLongDate(evidence.period_b.end)}
                            </span>
                          )}
                          {typeof evidence.record_count === "number" && <small>{evidence.record_count.toLocaleString()} metric records</small>}
                          {evidence.maintenance && <div className="maintenance-chat-evidence">
                            {evidence.maintenance.events?.slice(0, 6).map((event) => <a key={event.id} href={`/api/maintenance/events/${encodeURIComponent(event.id)}`} target="_blank" rel="noreferrer">
                              {event.event_date} · {event.equipment_label} · {event.action}
                            </a>)}
                            {evidence.maintenance.saved && <strong>Saved locally · revision history retained</strong>}
                            {evidence.maintenance.undo_available && <button type="button" onClick={() => void undoChatMaintenance(evidence.maintenance!)}>Undo maintenance action</button>}
                            {evidence.maintenance.events?.length ? <a href="#maintenance">Edit in Maintenance history</a> : null}
                            {evidence.maintenance.download_url && <a href={evidence.maintenance.download_url}>Download maintenance CSV</a>}
                            {evidence.maintenance.clarification_id && <small>Nothing saved yet. Reply with the missing detail to complete this entry.</small>}
                          </div>}
                          {evidence.proposal && (
                            <div className="settings-proposal">
                              <strong>{evidence.proposal.status === "saved" ? "Saved locally" : "Review proposed change"}</strong>
                              <table>
                                <thead><tr><th>Field</th><th>Current</th><th>Proposed</th></tr></thead>
                                <tbody>{proposalRows(evidence.proposal).map((row, index) => (
                                  <tr key={index}><td>{row.label}</td><td>{row.before}</td><td>{row.after}</td></tr>
                                ))}</tbody>
                              </table>
                              <button type="button" disabled={savingProposal !== null || evidence.proposal.status === "saved"}
                                onClick={() => void saveChatProposal(evidence.proposal!)}>
                                {savingProposal === evidence.proposal.id ? "Saving…" : evidence.proposal.status === "saved" ? "Saved" : "Save change"}
                              </button>
                              <a href="#settings">Edit in Settings</a>
                              <small>To revise this proposal, ask for a correction in chat. Changes use the same profile and goals as Settings.</small>
                            </div>
                          )}
                          {typeof evidence.total_matches === "number" && (
                            <small>
                              {evidence.total_matches.toLocaleString()} matching {evidence.tool === "find_same_course_rides" ? "course attempts" : evidence.tool === "find_similar_rides" ? "rides" : "activities"}
                              {typeof evidence.candidate_pool_count === "number" ? ` from ${evidence.candidate_pool_count.toLocaleString()} candidates` : ""}
                              {evidence.truncated ? ` · ${evidence.returned_count} shown` : ""}
                            </small>
                          )}
                          {(evidence.freshness?.latest_recorded_at || evidence.freshness?.latest_started_at) && (
                            <small>Fresh through {formatLongDate(evidence.freshness.latest_recorded_at ?? evidence.freshness.latest_started_at ?? "")}</small>
                          )}
                          {evidence.records && evidence.records.length > 0 && (
                            <div className="evidence-links">
                              {evidence.reference_record && (
                                <a href={`${evidence.reference_record.url}?timezone=${encodeURIComponent(browserTimeZone)}`} target="_blank" rel="noreferrer">
                                  Reference: {evidence.reference_record.name ?? evidence.reference_record.activity_type.replaceAll("_", " ")} · {formatLongDate(evidence.reference_record.local_date)}
                                </a>
                              )}
                              {evidence.records.slice(0, 6).map((record) => (
                                <a href={`${record.url}?timezone=${encodeURIComponent(browserTimeZone)}`} key={record.id} target="_blank" rel="noreferrer">
                                  {record.name ?? record.activity_type.replaceAll("_", " ")} · {formatLongDate(record.local_date)}
                                  {typeof record.similarity_score === "number" ? ` · ${record.similarity_score.toFixed(0)}% similarity` : ""}
                                  {typeof record.route_overlap_percent === "number" ? ` · ${record.route_overlap_percent.toFixed(0)}% route overlap` : ""}
                                  {record.direction ? ` · ${record.direction}` : ""}
                                </a>
                              ))}
                            </div>
                          )}
                          {evidence.reference_record && (!evidence.records || evidence.records.length === 0) && (
                            <div className="evidence-links">
                              <a href={`${evidence.reference_record.url}?timezone=${encodeURIComponent(browserTimeZone)}`} target="_blank" rel="noreferrer">
                                Reference: {evidence.reference_record.name ?? evidence.reference_record.activity_type.replaceAll("_", " ")} · {formatLongDate(evidence.reference_record.local_date)}
                              </a>
                            </div>
                          )}
                          {evidence.criteria && evidence.criteria.length > 0 && (
                            <div className="evidence-criteria">
                              {evidence.criteria.map((criterion) => (
                                <small key={criterion.field}>{formatSimilarityCriterion(criterion, preferredDistanceUnit)}</small>
                              ))}
                            </div>
                          )}
                          {evidence.unavailable_criteria && evidence.unavailable_criteria.length > 0 && (
                            <small>Not available for matching: {evidence.unavailable_criteria.join(", ")}</small>
                          )}
                          {evidence.course_progress && (
                            <div className="course-progress">
                              <strong>
                                {evidence.course_progress.attempt_count} matched attempts · {formatLongDate(evidence.course_progress.earliest.local_date)} to {formatLongDate(evidence.course_progress.latest.local_date)}
                              </strong>
                              {evidence.course_progress.changes_latest_minus_earliest.map((change) => (
                                <small key={change.metric}>
                                  {change.metric}: {formatCourseMetric(change.earliest, change.unit)} → {formatCourseMetric(change.latest, change.unit)}
                                  {change.percent === null ? "" : ` · ${change.percent >= 0 ? "+" : ""}${change.percent.toFixed(1)}%`}
                                </small>
                              ))}
                            </div>
                          )}
                          {evidence.privacy && <small>{evidence.privacy}</small>}
                          {evidence.missing_metric_types && evidence.missing_metric_types.length > 0 && (
                            <small>Not recorded: {evidence.missing_metric_types.join(", ")}</small>
                          )}
                        </div>
                      ))}
                    </div>
                  )}
                </article>
              ))}
            </div>
          )}

          <form
            className="chat-composer"
            onSubmit={(event) => {
              event.preventDefault();
              void sendChatMessage();
            }}
          >
            <label htmlFor="chat-question">Question about your stored data</label>
            <textarea
              id="chat-question"
              maxLength={4000}
              placeholder="For example: How has my running volume changed over the last eight weeks?"
              value={chatInput}
              onChange={(event) => setChatInput(event.target.value)}
              disabled={chatStatus.kind === "streaming"}
            />
            <div className="chat-actions">
              <span>
                {chatStatus.kind === "streaming"
                  ? chatStatus.slow
                    ? "Still working—local models can take longer."
                    : `Using ${chatStatus.model ?? "the selected model"}…`
                  : chatStatus.kind === "error"
                    ? chatStatus.message
                    : "Missing measurements are never filled with guesses."}
              </span>
              {chatStatus.kind === "streaming" ? (
                <button className="secondary-action" type="button" onClick={stopChatResponse}>Stop</button>
              ) : (
                <button type="submit" disabled={!chatInput.trim() || connection.kind !== "ready"}>Ask</button>
              )}
            </div>
          </form>
        </div>
      </section>

      <MaintenancePanel refreshToken={maintenanceVersion} timezone={browserTimeZone} onChanged={() => setMaintenanceVersion((current) => current + 1)} />

      <section className="coverage" id="data" aria-labelledby="coverage-title">
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

      <section className="settings" id="settings" aria-labelledby="settings-title">
        <div className="section-heading">
          <div>
            <p>Personal settings</p>
            <h2 id="settings-title">Profile and training goals</h2>
          </div>
        </div>
        {!settingsDraft ? (
          <p className="settings-message">Settings are available when the local backend is running.</p>
        ) : (
          <div className="settings-layout">
            <form
              className="settings-panel"
              onSubmit={(event) => {
                event.preventDefault();
                void saveProfileSettings();
              }}
            >
              <div className="settings-panel-heading">
                <div>
                  <span>Profile</span>
                  <h3>Optional personal details</h3>
                </div>
                <button type="submit" disabled={isSavingSettings}>Save profile</button>
              </div>
              <p>These values stay in the local database and can guide later planning.</p>
              <div className="settings-fields">
                <label>
                  Display name
                  <input
                    type="text"
                    maxLength={80}
                    value={settingsDraft.profile.display_name ?? ""}
                    onChange={(event) => setSettingsDraft({
                      ...settingsDraft,
                      profile: { ...settingsDraft.profile, display_name: event.target.value || null },
                    })}
                  />
                </label>
                <label>
                  Timezone
                  <input
                    type="text"
                    value={settingsDraft.profile.timezone ?? browserTimeZone}
                    onChange={(event) => setSettingsDraft({
                      ...settingsDraft,
                      profile: { ...settingsDraft.profile, timezone: event.target.value || null },
                    })}
                  />
                </label>
                <label>
                  Distance unit
                  <select
                    value={settingsDraft.profile.preferred_distance_unit}
                    onChange={(event) => setSettingsDraft({
                      ...settingsDraft,
                      profile: { ...settingsDraft.profile, preferred_distance_unit: event.target.value as "km" | "mi" },
                    })}
                  >
                    <option value="km">Kilometres</option>
                    <option value="mi">Miles</option>
                  </select>
                </label>
                <label>
                  Weight unit
                  <select
                    value={settingsDraft.profile.preferred_weight_unit}
                    onChange={(event) => setSettingsDraft({
                      ...settingsDraft,
                      profile: { ...settingsDraft.profile, preferred_weight_unit: event.target.value as "kg" | "lb" },
                    })}
                  >
                    <option value="kg">Kilograms</option>
                    <option value="lb">Pounds</option>
                  </select>
                </label>
                <label>
                  Birth date
                  <input
                    type="date"
                    value={settingsDraft.profile.birth_date ?? ""}
                    onChange={(event) => setSettingsDraft({
                      ...settingsDraft,
                      profile: { ...settingsDraft.profile, birth_date: event.target.value || null },
                    })}
                  />
                </label>
                <label>
                  Sex or gender
                  <input
                    type="text"
                    maxLength={40}
                    value={settingsDraft.profile.sex ?? ""}
                    onChange={(event) => setSettingsDraft({
                      ...settingsDraft,
                      profile: { ...settingsDraft.profile, sex: event.target.value || null },
                    })}
                  />
                </label>
                <label>
                  Height (cm)
                  <input
                    type="number"
                    min="50"
                    max="260"
                    step="0.1"
                    value={settingsDraft.profile.height_cm ?? ""}
                    onChange={(event) => setSettingsDraft({
                      ...settingsDraft,
                      profile: { ...settingsDraft.profile, height_cm: event.target.value ? Number(event.target.value) : null },
                    })}
                  />
                </label>
                <label>
                  Weight (kg)
                  <input
                    type="number"
                    min="20"
                    max="500"
                    step="0.1"
                    value={settingsDraft.profile.weight_kg ?? ""}
                    onChange={(event) => setSettingsDraft({
                      ...settingsDraft,
                      profile: { ...settingsDraft.profile, weight_kg: event.target.value ? Number(event.target.value) : null },
                    })}
                  />
                </label>
              </div>
            </form>

            <form
              className="settings-panel settings-panel--ai"
              onSubmit={(event) => {
                event.preventDefault();
                void saveAISettings();
              }}
            >
              <div className="settings-panel-heading">
                <div>
                  <span>AI providers</span>
                  <h3>OpenAI and local Qwen</h3>
                </div>
                <button type="submit" disabled={isSavingSettings}>Save AI settings</button>
              </div>
              <p>
                Choose which provider the assistant uses. Switching is manual, so the app
                never falls back to a paid API without your choice.
              </p>
              <div className="settings-fields settings-fields--ai">
                <label>
                  Active provider
                  <select
                    value={settingsDraft.ai.active_provider}
                    onChange={(event) => setSettingsDraft({
                      ...settingsDraft,
                      ai: {
                        ...settingsDraft.ai,
                        active_provider: event.target.value as AiProviderName,
                      },
                    })}
                  >
                    <option value="ollama">Qwen through Ollama</option>
                    <option value="openai">OpenAI API</option>
                  </select>
                </label>
                <label>
                  Ollama model
                  <input
                    type="text"
                    maxLength={100}
                    value={settingsDraft.ai.ollama_model}
                    onChange={(event) => setSettingsDraft({
                      ...settingsDraft,
                      ai: { ...settingsDraft.ai, ollama_model: event.target.value },
                    })}
                  />
                </label>
                <label>
                  OpenAI model
                  <input
                    type="text"
                    maxLength={100}
                    value={settingsDraft.ai.openai_model}
                    onChange={(event) => setSettingsDraft({
                      ...settingsDraft,
                      ai: { ...settingsDraft.ai, openai_model: event.target.value },
                    })}
                  />
                </label>
              </div>
              {connection.kind === "ready" && (
                <div className="ai-provider-status" aria-label="AI provider readiness">
                  {(["ollama", "openai"] as const).map((provider) => {
                    const status = connection.aiProviderStatus.providers[provider];
                    return (
                      <div key={provider} className={status.available ? "ai-provider-ready" : "ai-provider-attention"}>
                        <strong>{provider === "ollama" ? "Qwen / Ollama" : "OpenAI"}</strong>
                        <span>{status.available ? "Ready" : "Setup needed"}</span>
                        <small>{status.detail}</small>
                      </div>
                    );
                  })}
                </div>
              )}
              <p className="ai-key-note">
                OpenAI keys are read from <code>OPENAI_API_KEY</code> in the backend environment
                and are never saved in this database or displayed here.
              </p>
            </form>

            <form
              className="settings-panel settings-panel--goals"
              onSubmit={(event) => {
                event.preventDefault();
                void saveGoalSettings();
              }}
            >
              <div className="settings-panel-heading">
                <div>
                  <span>Goals</span>
                  <h3>Training direction</h3>
                </div>
                <div className="settings-actions">
                  <button className="secondary-action" type="button" onClick={addGoal}>Add goal</button>
                  <button type="submit" disabled={isSavingSettings}>Save goals</button>
                </div>
              </div>
              {settingsDraft.goals.length === 0 ? (
                <p>No goals saved. Goals are optional and can be added when useful.</p>
              ) : settingsDraft.goals.map((goal, index) => (
                <fieldset className="goal-editor" key={goal.id ?? `new-${index}`}>
                  <legend>Goal {index + 1}</legend>
                  <div className="settings-fields">
                    <label>
                      Title
                      <input
                        type="text"
                        required
                        maxLength={120}
                        value={goal.title}
                        onChange={(event) => updateGoal(index, { title: event.target.value })}
                      />
                    </label>
                    <label>
                      Type
                      <select value={goal.goal_type} onChange={(event) => updateGoal(index, { goal_type: event.target.value })}>
                        <option value="general">General</option>
                        <option value="cycling">Cycling</option>
                        <option value="running">Running</option>
                        <option value="strength">Strength</option>
                        <option value="health">Health</option>
                      </select>
                    </label>
                    <label>
                      Target
                      <input
                        type="number"
                        min="0"
                        step="any"
                        value={goal.target_value ?? ""}
                        onChange={(event) => updateGoal(index, { target_value: event.target.value ? Number(event.target.value) : null })}
                      />
                    </label>
                    <label>
                      Target unit
                      <input type="text" maxLength={30} value={goal.target_unit ?? ""} onChange={(event) => updateGoal(index, { target_unit: event.target.value || null })} />
                    </label>
                    <label>
                      Target date
                      <input type="date" value={goal.target_date ?? ""} onChange={(event) => updateGoal(index, { target_date: event.target.value || null })} />
                    </label>
                    <label>
                      Status
                      <select value={goal.status} onChange={(event) => updateGoal(index, { status: event.target.value as UserGoal["status"] })}>
                        <option value="active">Active</option>
                        <option value="paused">Paused</option>
                        <option value="achieved">Achieved</option>
                      </select>
                    </label>
                  </div>
                  <label className="goal-notes">
                    Notes
                    <textarea maxLength={1000} value={goal.notes ?? ""} onChange={(event) => updateGoal(index, { notes: event.target.value || null })} />
                  </label>
                  <button className="remove-goal" type="button" onClick={() => removeGoal(index)}>Remove goal</button>
                </fieldset>
              ))}
            </form>
          </div>
        )}
        {settingsMessage && <p className="settings-message" role="status">{settingsMessage}</p>}
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
