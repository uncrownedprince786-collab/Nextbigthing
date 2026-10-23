import { plainPrice } from "@/lib/format";
import type { Bar } from "@/lib/intradayFeatures";

/// The bars the forecast was actually read from, with the horizon it reaches into.
///
/// **It draws the model's own input, not a decorative price line.** The series here is the tail of
/// the exact window `featuresAt` consumed, the dashed level is the reference close the direction
/// was measured from, and the shaded panel on the right is the horizon -- so the picture and the
/// verdict beneath it cannot describe different moments. A chart fetched separately could, and
/// did: the asset page's daily sparkline ends at the last stored *session*, which on a five-minute
/// forecast is up to a day behind the bar the model read.
///
/// Inline SVG, no client JavaScript and no chart library, like every other figure on this site.
export function ForecastChart({
  bars,
  stepMs,
  reference,
  horizonMinutes,
  horizonLabel,
  direction,
  symbol,
  show = 144,
  width = 720,
  height = 200,
}: {
  bars: Bar[];
  stepMs: number;
  reference: number;
  horizonMinutes: number;
  horizonLabel: string;
  /// Null when the model read this window and did not call it: the bars and the horizon are drawn
  /// exactly as they are, and nothing is drawn into the shaded panel. A flat arrow would be a
  /// third claim -- "sideways" -- that the binary model never makes, and no arrow at all is the
  /// only honest picture of a silence.
  direction: "UP" | "DOWN" | null;
  symbol: string;
  show?: number;
  width?: number;
  height?: number;
}) {
  const series = bars.slice(Math.max(0, bars.length - show));
  if (series.length < 2) {
    return (
      <p className="text-muted-foreground text-sm">
        Not enough bars to draw {symbol}.
      </p>
    );
  }

  // The forward panel is sized in bars, so an hour ahead on a 5-minute series takes twelve
  // columns and an hour ahead on a 4-hour series takes a quarter of one. The reader sees the
  // reach of the question against the history behind it rather than a fixed-width box.
  const forwardBars = Math.max(1, Math.round((horizonMinutes * 60_000) / stepMs));
  const columns = series.length + forwardBars;

  const highs = series.map((b) => b.h);
  const lows = series.map((b) => b.l);
  const min = Math.min(...lows, reference);
  const max = Math.max(...highs, reference);
  const span = max - min || 1;

  const padX = 2;
  const padY = 8;
  const w = width - padX * 2;
  const h = height - padY * 2;
  const step = w / (columns - 1);
  const yOf = (v: number) => padY + h - ((v - min) / span) * h;
  const xOf = (i: number) => padX + i * step;

  const line = series.map((b, i) => `${xOf(i).toFixed(1)},${yOf(b.c).toFixed(1)}`).join(" ");
  // The high/low envelope, as one closed path: the range each bar covered, which a close-only
  // line hides entirely. It is the difference between a quiet hour and a violent one that
  // happened to end where it started.
  const bandTop = series.map((b, i) => `${xOf(i).toFixed(1)},${yOf(b.h).toFixed(1)}`);
  const bandBottom = series
    .map((b, i) => `${xOf(i).toFixed(1)},${yOf(b.l).toFixed(1)}`)
    .reverse();
  const band = `${bandTop.join(" ")} ${bandBottom.join(" ")}`;

  const first = series[0];
  const last = series[series.length - 1];
  const change = (last.c / first.c - 1) * 100;
  const stroke = change >= 0 ? "var(--up)" : "var(--down)";
  const arrow = direction === null
    ? "currentColor"
    : direction === "UP" ? "var(--up)" : "var(--down)";
  const xNow = xOf(series.length - 1);
  const xEnd = xOf(columns - 1);
  const yNow = yOf(reference);
  // The arrow is a direction, never a magnitude: it rises or falls by a fixed fraction of the
  // panel. The model predicts a sign and nothing else, and a slope drawn from a probability
  // would be a size claim it never made.
  const yEnd = direction === "UP" ? yNow - h * 0.18 : yNow + h * 0.18;

  const hhmm = (ms: number) => new Date(ms).toISOString().slice(5, 16).replace("T", " ");

  return (
    <figure>
      <svg
        viewBox={`0 0 ${width} ${height}`}
        className="h-auto w-full"
        role="img"
        aria-label={
          `${symbol}: ${series.length} bars to ${hhmm(last.ts + stepMs)} UTC at ` +
          `${plainPrice(last.c)}, ` +
          (direction === null
            ? `with no call over ${horizonLabel.toLowerCase()}`
            : `with a ${direction} call over ${horizonLabel.toLowerCase()}`)
        }
      >
        {/* The horizon, as the part of the picture that has not happened yet. */}
        <rect
          x={xNow}
          y={padY}
          width={Math.max(xEnd - xNow, 1)}
          height={h}
          fill="currentColor"
          opacity="0.05"
        />
        <polygon points={band} fill={stroke} opacity="0.12" />
        <polyline points={line} fill="none" stroke={stroke} strokeWidth="1.5" strokeLinejoin="round" />
        {/* The close the direction was measured from. Everything the verdict says is relative
            to this level, so it is drawn rather than left to be inferred from the line's end. */}
        <line
          x1={padX}
          y1={yNow}
          x2={xEnd}
          y2={yNow}
          stroke="currentColor"
          strokeWidth="1"
          strokeDasharray="3 3"
          opacity="0.45"
        />
        <circle cx={xNow} cy={yNow} r="3" fill={arrow} opacity={direction === null ? 0.5 : 1} />
        {direction === null ? null : (
          <>
            <line x1={xNow} y1={yNow} x2={xEnd} y2={yEnd} stroke={arrow} strokeWidth="2" />
            <polygon
              points={
                direction === "UP"
                  ? `${xEnd},${yEnd} ${xEnd - 7},${yEnd + 4} ${xEnd - 7},${yEnd - 4}`
                  : `${xEnd},${yEnd} ${xEnd - 7},${yEnd - 4} ${xEnd - 7},${yEnd + 4}`
              }
              fill={arrow}
            />
          </>
        )}
      </svg>
      <figcaption className="text-muted-foreground num mt-1 flex flex-wrap justify-between gap-x-3 text-[11px]">
        <span>
          {hhmm(first.ts)} UTC {plainPrice(first.c)}
        </span>
        <span>
          {series.length} bars · high {plainPrice(max)} low {plainPrice(min)}
        </span>
        <span>
          last close {hhmm(last.ts + stepMs)} UTC {plainPrice(last.c)}
        </span>
      </figcaption>
      <p className="text-muted-foreground mt-1 text-[11px]">
        The shaded panel on the right is {horizonLabel.toLowerCase()} — the window the direction is
        about.{" "}
        {direction === null
          ? "It is empty because the model made no call over it. These are the bars it read, and they are drawn whether or not it had anything to say about them."
          : "The arrow is a sign, not a size: the model predicts which way, never how far."}
      </p>
    </figure>
  );
}
