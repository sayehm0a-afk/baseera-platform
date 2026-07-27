"use client";

import { useEffect, useRef } from "react";
import {
  CandlestickSeries,
  createChart,
  HistogramSeries,
  type IChartApi,
  type ISeriesApi,
  type UTCTimestamp,
} from "lightweight-charts";
import type { HistoricalBar } from "@/lib/api/stocks-types";

export interface PriceLevel {
  price: number;
  label: string;
  color: string;
}

interface PriceChartProps {
  bars: HistoricalBar[];
  /** Entry/target/stop-loss levels drawn as horizontal price lines on
   * the candlestick series -- the "recommendation markers" the
   * stock-detail page requires. Never invented here: the caller
   * (StockDetailClient) passes only what /decision actually returned. */
  levels?: PriceLevel[];
  className?: string;
}

/** Candlestick + volume chart over real, already-fetched OHLCV bars
 * (src/api/routes/stocks.py's `/{symbol}/history`, no synthetic data
 * generated here). Built on lightweight-charts (TradingView's own
 * open-source charting library, Apache-2.0, zero dependencies) --
 * chosen for native candlestick/volume support, small bundle size, and
 * proven performance on financial time series; evaluated against the
 * alternatives (recharts/visx have no first-class candlestick type,
 * d3 would mean building OHLC rendering from scratch).
 *
 * The chart canvas itself is deliberately kept `dir="ltr"` even inside
 * an RTL page: financial candlestick charts read chronologically
 * left-to-right by near-universal convention (including on Arabic
 * financial platforms), matching this codebase's own established rule
 * that financial numerals render in tabular Western digits
 * (`.bsr-numeric`) regardless of page direction -- only the
 * surrounding labels/legend are RTL Arabic.
 */
export function PriceChart({ bars, levels, className }: PriceChartProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const candleSeriesRef = useRef<ISeriesApi<"Candlestick"> | null>(null);

  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;

    const chart = createChart(container, {
      autoSize: true,
      layout: {
        background: { color: "transparent" },
        textColor: "#9AA5B1",
      },
      grid: {
        vertLines: { color: "rgba(148, 163, 184, 0.08)" },
        horzLines: { color: "rgba(148, 163, 184, 0.08)" },
      },
      rightPriceScale: { borderVisible: false },
      timeScale: { borderVisible: false, timeVisible: false },
    });
    chartRef.current = chart;

    const candleSeries = chart.addSeries(CandlestickSeries, {
      upColor: "#1FA97A",
      downColor: "#E5484D",
      borderVisible: false,
      wickUpColor: "#1FA97A",
      wickDownColor: "#E5484D",
    });
    candleSeriesRef.current = candleSeries;

    const volumeSeries = chart.addSeries(
      HistogramSeries,
      {
        priceFormat: { type: "volume" },
        priceScaleId: "volume",
      },
      1
    );
    chart.panes()[1]?.setHeight(80);

    return () => {
      chart.remove();
      chartRef.current = null;
      candleSeriesRef.current = null;
      void volumeSeries;
    };
    // Series/chart are recreated whenever the container mounts; bar
    // and level data are pushed in the effects below instead of
    // re-running this whole setup, so panning/zoom state survives a
    // new data fetch (e.g. switching symbols keeps the same chart
    // instance only when the component itself doesn't remount --
    // React keys the component by symbol at the call site, so a full
    // recreation on symbol change is intentional, not a leak).
  }, []);

  useEffect(() => {
    const candleSeries = candleSeriesRef.current;
    const chart = chartRef.current;
    if (!candleSeries || !chart) return;

    const sorted = [...bars].sort(
      (a, b) => new Date(a.timestamp).getTime() - new Date(b.timestamp).getTime()
    );

    candleSeries.setData(
      sorted.map((bar) => ({
        time: (new Date(bar.timestamp).getTime() / 1000) as UTCTimestamp,
        open: bar.open,
        high: bar.high,
        low: bar.low,
        close: bar.close,
      }))
    );

    const volumeSeries = chart
      .panes()[1]
      ?.getSeries()
      .find((s) => s.seriesType() === "Histogram") as ISeriesApi<"Histogram"> | undefined;
    volumeSeries?.setData(
      sorted.map((bar) => ({
        time: (new Date(bar.timestamp).getTime() / 1000) as UTCTimestamp,
        value: bar.volume,
        color: bar.close >= bar.open ? "rgba(31, 169, 122, 0.5)" : "rgba(229, 72, 77, 0.5)",
      }))
    );

    chart.timeScale().fitContent();
  }, [bars]);

  useEffect(() => {
    const candleSeries = candleSeriesRef.current;
    if (!candleSeries) return;

    const priceLines = (levels ?? []).map((level) =>
      candleSeries.createPriceLine({
        price: level.price,
        color: level.color,
        lineWidth: 1,
        lineStyle: 2,
        axisLabelVisible: true,
        title: level.label,
      })
    );

    return () => {
      priceLines.forEach((line) => candleSeries.removePriceLine(line));
    };
  }, [levels]);

  return (
    <div
      ref={containerRef}
      dir="ltr"
      className={`h-[360px] w-full sm:h-[440px] ${className ?? ""}`}
    />
  );
}
