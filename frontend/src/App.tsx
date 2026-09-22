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

type ConnectionState =
  | { kind: "checking" }
  | { kind: "ready"; health: HealthResponse; summary: HistorySummary }
  | { kind: "offline" };

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

export default function App() {
  const [connection, setConnection] = useState<ConnectionState>({
    kind: "checking",
  });

  useEffect(() => {
    const controller = new AbortController();

    Promise.all([
      fetch("/api/health", { signal: controller.signal }),
      fetch("/api/history/summary", { signal: controller.signal }),
    ])
      .then(async ([healthResponse, summaryResponse]) => {
        if (!healthResponse.ok || !summaryResponse.ok) {
          throw new Error("Backend is unavailable");
        }
        const [health, summary] = await Promise.all([
          healthResponse.json() as Promise<HealthResponse>,
          summaryResponse.json() as Promise<HistorySummary>,
        ]);
        setConnection({ kind: "ready", health, summary });
      })
      .catch((error: unknown) => {
        if (error instanceof DOMException && error.name === "AbortError") return;
        setConnection({ kind: "offline" });
      });

    return () => controller.abort();
  }, []);

  const statusText =
    connection.kind === "ready"
      ? `Connected · ${connection.health.schema.tables} database tables`
      : connection.kind === "offline"
        ? "Backend is not running"
        : "Checking local backend…";

  const summary = connection.kind === "ready" ? connection.summary : null;
  const previewCards = [
    {
      label: "Latest steps",
      value: summary?.latest_steps
        ? Math.round(summary.latest_steps.value).toLocaleString()
        : "—",
      detail: summary?.latest_steps ? "Daily total" : "No step data loaded",
    },
    {
      label: "Last activity",
      value: summary?.latest_activity?.name ?? "—",
      detail: summary?.latest_activity
        ? summary.latest_activity.activity_type.replaceAll("_", " ")
        : "No activities loaded",
    },
    {
      label: "Loaded records",
      value: summary
        ? (summary.activity_count + summary.metric_count).toLocaleString()
        : "—",
      detail: summary
        ? `${summary.activity_count} activities · ${summary.metric_count} metrics`
        : "Waiting for local data",
    },
  ];

  return (
    <main>
      <header className="hero">
        <p className="eyebrow">Personal health workspace</p>
        <h1>Your training history,<br />kept close.</h1>
        <p className="intro">
          The local foundation is ready. Garmin imports, dashboard metrics, and
          analysis will be added on top of this private core.
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
          {summary?.data_mode === "synthetic" && (
            <div className="synthetic-label">Synthetic data · not Garmin data</div>
          )}
        </div>
        <div className="preview-grid">
          {previewCards.map((card) => (
            <article className="data-card" key={card.label}>
              <p>{card.label}</p>
              <h3>{card.value}</h3>
              <span>{card.detail}</span>
            </article>
          ))}
        </div>
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
