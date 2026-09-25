import { useState } from "react";
import { Bar, BarChart, CartesianGrid, LabelList, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { Table2 } from "lucide-react";

/** Single-series bar chart: one hue, thin rounded bars, recessive grid, hover tooltip and a table view. */
export function BarViz({ data, x, y, horizontal, height = 240, suffix = "", valueLabel = "Count", labels = false }: {
  data: Record<string, any>[];
  x: string;
  y: string;
  horizontal?: boolean;
  height?: number;
  suffix?: string;
  valueLabel?: string;
  labels?: boolean;
}) {
  const [table, setTable] = useState(false);
  const empty = !data.length || data.every((d) => !d[y]);
  if (empty) return <div className="flex items-center justify-center text-sm text-slate-400" style={{ height }}>No data yet</div>;

  const axis = { fontSize: 12, fill: "var(--viz-axis)" };
  const tooltip = (
    <Tooltip
      cursor={{ fill: "var(--viz-grid)", opacity: 0.5 }}
      contentStyle={{ background: "var(--viz-surface)", border: "1px solid var(--viz-grid)", borderRadius: 8, fontSize: 12, color: "var(--viz-axis)" }}
      labelStyle={{ color: "var(--viz-axis)", fontWeight: 600 }}
      formatter={(v: any) => [`${v}${suffix}`, valueLabel]}
    />
  );
  return (
    <div className="relative">
      <button onClick={() => setTable((t) => !t)} aria-label={table ? "Show chart" : "Show table"}
        className="absolute -top-1 right-0 z-10 rounded p-1 text-slate-400 hover:bg-slate-100 dark:hover:bg-slate-800">
        <Table2 className="h-4 w-4" />
      </button>
      {table ? (
        <div className="overflow-auto pt-6" style={{ maxHeight: height }}>
          <table className="w-full text-sm">
            <thead><tr className="text-left text-xs text-slate-500"><th className="py-1">{x}</th><th className="py-1 text-right">{valueLabel}</th></tr></thead>
            <tbody>{data.map((d) => <tr key={String(d[x])} className="border-t border-slate-100 dark:border-slate-800"><td className="py-1">{d[x]}</td><td className="py-1 text-right">{d[y]}{suffix}</td></tr>)}</tbody>
          </table>
        </div>
      ) : (
        <ResponsiveContainer width="100%" height={height}>
          {horizontal ? (
            <BarChart data={data} layout="vertical" margin={{ top: 8, right: 36, left: 8, bottom: 0 }}>
              <CartesianGrid horizontal={false} stroke="var(--viz-grid)" />
              <XAxis type="number" tick={axis} axisLine={false} tickLine={false} allowDecimals={false} />
              <YAxis type="category" dataKey={x} tick={axis} axisLine={false} tickLine={false} width={120} />
              {tooltip}
              <Bar dataKey={y} fill="var(--viz-series-1)" radius={[0, 4, 4, 0]} maxBarSize={24} isAnimationActive={false}>
                {labels && <LabelList dataKey={y} position="right" formatter={(v: any) => `${v}${suffix}`} style={{ fontSize: 11, fill: "var(--viz-axis)" }} />}
              </Bar>
            </BarChart>
          ) : (
            <BarChart data={data} margin={{ top: 16, right: 8, left: -12, bottom: 0 }}>
              <CartesianGrid vertical={false} stroke="var(--viz-grid)" />
              <XAxis dataKey={x} tick={axis} axisLine={false} tickLine={false} interval="preserveStartEnd" />
              <YAxis tick={axis} axisLine={false} tickLine={false} allowDecimals={false} />
              {tooltip}
              <Bar dataKey={y} fill="var(--viz-series-1)" radius={[4, 4, 0, 0]} maxBarSize={24} isAnimationActive={false}>
                {labels && <LabelList dataKey={y} position="top" formatter={(v: any) => (v ? `${v}${suffix}` : "")} style={{ fontSize: 11, fill: "var(--viz-axis)" }} />}
              </Bar>
            </BarChart>
          )}
        </ResponsiveContainer>
      )}
    </div>
  );
}
