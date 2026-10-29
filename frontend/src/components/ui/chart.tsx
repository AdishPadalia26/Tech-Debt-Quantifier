"use client";

import * as React from "react";
import * as RechartsPrimitive from "recharts";

import { cn } from "@/lib/utils";

/**
 * shadcn/ui chart primitives (recharts 3). ChartContainer injects per-series
 * colors as `--color-<key>` CSS variables from a ChartConfig; the tooltip and
 * legend components read the same config so all charts share one style.
 */

export type ChartConfig = {
  [key: string]: {
    label?: React.ReactNode;
    icon?: React.ComponentType;
    color?: string;
  };
};

type ChartContextProps = { config: ChartConfig };

const ChartContext = React.createContext<ChartContextProps | null>(null);

function useChart() {
  const context = React.useContext(ChartContext);
  if (!context) {
    throw new Error("useChart must be used within a <ChartContainer />");
  }
  return context;
}

const ChartStyle = ({ id, config }: { id: string; config: ChartConfig }) => {
  const colorConfig = Object.entries(config).filter(([, c]) => c.color);
  if (!colorConfig.length) return null;
  const css = `[data-chart=${id}] {\n${colorConfig
    .map(([key, c]) => `  --color-${key}: ${c.color};`)
    .join("\n")}\n}`;
  return <style dangerouslySetInnerHTML={{ __html: css }} />;
};

const ChartContainer = React.forwardRef<
  HTMLDivElement,
  React.ComponentProps<"div"> & {
    config: ChartConfig;
    children: React.ComponentProps<
      typeof RechartsPrimitive.ResponsiveContainer
    >["children"];
  }
>(({ id, className, children, config, ...props }, ref) => {
  const uniqueId = React.useId();
  const chartId = `chart-${id || uniqueId.replace(/:/g, "")}`;

  return (
    <ChartContext.Provider value={{ config }}>
      <div
        data-chart={chartId}
        ref={ref}
        className={cn(
          "flex aspect-video justify-center text-xs",
          "[&_.recharts-cartesian-axis-tick_text]:fill-muted-foreground",
          "[&_.recharts-cartesian-grid_line[stroke='#ccc']]:stroke-border/50",
          "[&_.recharts-curve.recharts-tooltip-cursor]:stroke-border",
          "[&_.recharts-dot[stroke='#fff']]:stroke-transparent",
          "[&_.recharts-layer]:outline-none [&_.recharts-sector]:outline-none",
          "[&_.recharts-sector[stroke='#fff']]:stroke-transparent",
          "[&_.recharts-surface]:outline-none",
          className
        )}
        {...props}
      >
        <ChartStyle id={chartId} config={config} />
        <RechartsPrimitive.ResponsiveContainer>
          {children}
        </RechartsPrimitive.ResponsiveContainer>
      </div>
    </ChartContext.Provider>
  );
});
ChartContainer.displayName = "ChartContainer";

const ChartTooltip = RechartsPrimitive.Tooltip;

type TooltipPayloadItem = {
  dataKey?: string | number;
  name?: string | number;
  value?: number | string | Array<number | string>;
  color?: string;
  fill?: string;
  payload?: Record<string, unknown>;
  type?: string;
};

const ChartTooltipContent = React.forwardRef<
  HTMLDivElement,
  React.ComponentProps<"div"> & {
    active?: boolean;
    payload?: readonly TooltipPayloadItem[];
    label?: React.ReactNode;
    hideLabel?: boolean;
    hideIndicator?: boolean;
    nameKey?: string;
    labelFormatter?: (
      label: React.ReactNode,
      payload: readonly TooltipPayloadItem[]
    ) => React.ReactNode;
    formatter?: (
      value: number | string,
      name: string,
      item: TooltipPayloadItem
    ) => React.ReactNode;
  }
>(
  (
    {
      active,
      payload,
      className,
      hideLabel = false,
      hideIndicator = false,
      label,
      labelFormatter,
      formatter,
      nameKey,
    },
    ref
  ) => {
    const { config } = useChart();

    if (!active || !payload?.length) return null;

    const resolveLabel = (item: TooltipPayloadItem): React.ReactNode => {
      const key = String(nameKey || item.dataKey || item.name || "value");
      return config[key]?.label ?? item.name ?? key;
    };

    const header =
      !hideLabel && label != null
        ? labelFormatter
          ? labelFormatter(label, payload)
          : label
        : null;

    return (
      <div
        ref={ref}
        className={cn(
          "grid min-w-[8rem] max-w-[16rem] items-start gap-1.5 rounded-lg border border-border bg-popover px-2.5 py-1.5 text-xs text-popover-foreground shadow-xl",
          className
        )}
      >
        {header ? <div className="break-words font-medium">{header}</div> : null}
        <div className="grid gap-1.5">
          {payload
            .filter((item) => item.type !== "none")
            .map((item, index) => {
              const name = String(resolveLabel(item));
              const indicator = item.color || item.fill;
              const value = Array.isArray(item.value) ? item.value[0] : item.value;
              return (
                <div
                  key={`${item.dataKey ?? item.name}-${index}`}
                  className="flex items-center gap-2"
                >
                  {!hideIndicator && (
                    <span
                      aria-hidden
                      className="size-2.5 shrink-0 rounded-[2px]"
                      style={{ backgroundColor: indicator }}
                    />
                  )}
                  <span className="text-muted-foreground">{name}</span>
                  <span className="tabular ml-auto pl-3 font-mono font-medium text-foreground">
                    {formatter && value !== undefined
                      ? formatter(value, name, item)
                      : typeof value === "number"
                        ? value.toLocaleString("en-US")
                        : value}
                  </span>
                </div>
              );
            })}
        </div>
      </div>
    );
  }
);
ChartTooltipContent.displayName = "ChartTooltipContent";

const ChartLegend = RechartsPrimitive.Legend;

type LegendPayloadItem = {
  value?: string | number;
  dataKey?: unknown;
  color?: string;
  type?: string;
};

const ChartLegendContent = React.forwardRef<
  HTMLDivElement,
  React.ComponentProps<"div"> & {
    payload?: readonly LegendPayloadItem[];
    verticalAlign?: "top" | "middle" | "bottom";
    nameKey?: string;
  }
>(({ className, payload, verticalAlign = "bottom", nameKey }, ref) => {
  const { config } = useChart();
  if (!payload?.length) return null;

  return (
    <div
      ref={ref}
      className={cn(
        "flex flex-wrap items-center justify-center gap-x-4 gap-y-1",
        verticalAlign === "top" ? "pb-3" : "pt-3",
        className
      )}
    >
      {payload
        .filter((item) => item.type !== "none")
        .map((item, index) => {
          const key = String(
            nameKey || (typeof item.dataKey === "string" ? item.dataKey : item.value) || "value"
          );
          const itemConfig = config[key];
          return (
            <div key={`${key}-${index}`} className="flex items-center gap-1.5">
              <span
                aria-hidden
                className="size-2 shrink-0 rounded-[2px]"
                style={{ backgroundColor: item.color }}
              />
              {itemConfig?.label ?? item.value}
            </div>
          );
        })}
    </div>
  );
});
ChartLegendContent.displayName = "ChartLegendContent";

export {
  ChartContainer,
  ChartTooltip,
  ChartTooltipContent,
  ChartLegend,
  ChartLegendContent,
  ChartStyle,
};
