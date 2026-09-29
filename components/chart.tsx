import { isoDate } from "@/lib/format";

/// Inline SVG so the chart needs no client side JavaScript and no chart library.
export function Sparkline({
  points,
  width = 640,
  height = 140,
  label,
}: {
  points: { date: Date | string; close: number }[];
  width?: number;
  height?: number;
  label: string;
}) {
  if (points.length < 2) {
    return (
      <p className="text-muted-foreground text-sm">
        Not enough stored prices to draw a line for {label}.
      </p>
    );
  }
  const values = points.map((p) => p.close);
  const min = Math.min(...values);
  const max = Math.max(...values);
  const span = max - min || 1;
  const pad = 4;
  const w = width - pad * 2;
  const h = height - pad * 2;
  const step = w / (points.length - 1);
  const coords = points.map((p, i) => {
    const x = pad + i * step;
    const y = pad + h - ((p.close - min) / span) * h;
    return `${x.toFixed(1)},${y.toFixed(1)}`;
  });
  const first = points[0];
  const last = points[points.length - 1];
  const change = ((last.close / first.close - 1) * 100);
  const stroke = change >= 0 ? "var(--up)" : "var(--down)";

  return (
    <figure>
      <svg
        viewBox={`0 0 ${width} ${height}`}
        className="h-auto w-full"
        role="img"
        aria-label={`${label} price from ${isoDate(first.date)} to ${isoDate(last.date)}`}
      >
        <polyline
          points={coords.join(" ")}
          fill="none"
          stroke={stroke}
          strokeWidth="1.5"
          strokeLinejoin="round"
        />
      </svg>
      <figcaption className="text-muted-foreground num mt-1 flex flex-wrap justify-between text-[11px]">
        <span>
          {isoDate(first.date)} {first.close.toFixed(2)}
        </span>
        <span>
          high {max.toFixed(2)} low {min.toFixed(2)}
        </span>
        <span>
          {isoDate(last.date)} {last.close.toFixed(2)}
        </span>
      </figcaption>
    </figure>
  );
}

export function Bar({
  value,
  max,
  tone = "primary",
}: {
  value: number;
  max: number;
  tone?: "primary" | "up" | "down";
}) {
  const w = max === 0 ? 0 : Math.min(100, Math.abs(value / max) * 100);
  const color = tone === "primary" ? "var(--primary)" : tone === "up" ? "var(--up)" : "var(--down)";
  return (
    <div className="bg-muted h-1.5 w-full overflow-hidden rounded-full">
      <div className="h-full rounded-full" style={{ width: `${w}%`, background: color }} />
    </div>
  );
}
