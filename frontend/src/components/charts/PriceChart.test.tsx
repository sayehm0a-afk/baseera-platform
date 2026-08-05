import { describe, expect, it, vi } from "vitest";
import { cleanup, render } from "@testing-library/react";
import { afterEach } from "vitest";

/** Phase 2 Foundation Cleanup, goal 4: production-grade coverage for
 * the candlestick/volume chart -- the component every recommendation
 * "price levels" overlay renders through. lightweight-charts draws to
 * a real <canvas> 2D context jsdom does not implement, so the module
 * is mocked here (not the component itself): these tests assert
 * PriceChart's *own* wiring -- what it calls the charting library with
 * and how it reacts to prop changes/unmount -- not the library's
 * internal rendering, which is TradingView's concern, not this
 * codebase's. */

const { createChartMock, chartsCreated } = vi.hoisted(() => {
  const chartsCreated: Array<{
    addSeries: ReturnType<typeof vi.fn>;
    removeSeries: ReturnType<typeof vi.fn>;
    panes: ReturnType<typeof vi.fn>;
    timeScale: ReturnType<typeof vi.fn>;
    remove: ReturnType<typeof vi.fn>;
    candleSeries: ReturnType<typeof makeSeries>;
    volumeSeries: ReturnType<typeof makeSeries>;
    volumePane: { setHeight: ReturnType<typeof vi.fn>; getSeries: ReturnType<typeof vi.fn> };
    lineSeriesCreated: ReturnType<typeof makeSeries>[];
  }> = [];

  function makeSeries(seriesType: string) {
    return {
      setData: vi.fn(),
      createPriceLine: vi.fn((opts: unknown) => ({ opts })),
      removePriceLine: vi.fn(),
      seriesType: () => seriesType,
    };
  }

  function createChartMock() {
    const candleSeries = makeSeries("Candlestick");
    const volumeSeries = makeSeries("Histogram");
    const volumePane = { setHeight: vi.fn(), getSeries: vi.fn(() => [volumeSeries]) };
    const lineSeriesCreated: ReturnType<typeof makeSeries>[] = [];

    const chart = {
      addSeries: vi.fn((marker: unknown) => {
        if (marker === "CandlestickSeriesMarker") return candleSeries;
        if (marker === "LineSeriesMarker") {
          const lineSeries = makeSeries("Line");
          lineSeriesCreated.push(lineSeries);
          return lineSeries;
        }
        return volumeSeries;
      }),
      removeSeries: vi.fn(),
      panes: vi.fn(() => [{}, volumePane]),
      timeScale: vi.fn(() => ({ fitContent: vi.fn() })),
      remove: vi.fn(),
      candleSeries,
      volumeSeries,
      volumePane,
      lineSeriesCreated,
    };
    chartsCreated.push(chart);
    return chart;
  }

  return { createChartMock, chartsCreated };
});

vi.mock("lightweight-charts", () => ({
  createChart: createChartMock,
  CandlestickSeries: "CandlestickSeriesMarker",
  HistogramSeries: "HistogramSeriesMarker",
  LineSeries: "LineSeriesMarker",
}));

import { PriceChart } from "./PriceChart";
import type { HistoricalBar, MovingAveragePoint } from "@/lib/api/stocks-types";

afterEach(() => {
  cleanup();
  chartsCreated.length = 0;
});

const BARS: HistoricalBar[] = [
  { timestamp: "2026-08-04T00:00:00Z", open: 27.0, high: 27.5, low: 26.8, close: 27.3, volume: 1_500_000 },
  { timestamp: "2026-08-03T00:00:00Z", open: 26.7, high: 27.1, low: 26.6, close: 26.9, volume: 1_200_000 },
  { timestamp: "2026-08-05T00:00:00Z", open: 27.3, high: 27.6, low: 27.0, close: 27.1, volume: 900_000 },
];

describe("PriceChart", () => {
  it("renders its container with the deliberate ltr direction inside an RTL page", () => {
    const { container } = render(<PriceChart bars={BARS} />);
    const chartDiv = container.firstElementChild;
    expect(chartDiv).toHaveAttribute("dir", "ltr");
  });

  it("creates exactly one candlestick series and one histogram series on mount", () => {
    render(<PriceChart bars={BARS} />);
    const chart = chartsCreated[0];
    expect(chart.addSeries).toHaveBeenCalledTimes(2);
    expect(chart.addSeries.mock.calls[0][0]).toBe("CandlestickSeriesMarker");
    expect(chart.addSeries.mock.calls[1][0]).toBe("HistogramSeriesMarker");
  });

  it("sorts bars chronologically before pushing them into the candlestick series, regardless of input order", () => {
    render(<PriceChart bars={BARS} />);
    const chart = chartsCreated[0];
    const pushedCandles = chart.candleSeries.setData.mock.calls[0][0] as Array<{ time: number }>;
    const times = pushedCandles.map((c) => c.time);
    expect(times).toEqual([...times].sort((a, b) => a - b));
    expect(pushedCandles).toHaveLength(3);
  });

  it("colors an up bar's volume green and a down bar's volume red, never inventing a third color", () => {
    render(<PriceChart bars={BARS} />);
    const chart = chartsCreated[0];
    const pushedVolume = chart.volumeSeries.setData.mock.calls[0][0] as Array<{ color: string }>;
    const colors = new Set(pushedVolume.map((v) => v.color));
    expect(colors.size).toBeLessThanOrEqual(2);
    for (const color of colors) {
      expect(color === "rgba(31, 169, 122, 0.5)" || color === "rgba(229, 72, 77, 0.5)").toBe(true);
    }
  });

  it("draws exactly one price line per recommendation level, with the caller's own price/label/color", () => {
    render(
      <PriceChart
        bars={BARS}
        levels={[
          { price: 26.46, label: "وقف الخسارة", color: "red" },
          { price: 27.7, label: "الهدف الأول", color: "green" },
        ]}
      />
    );
    const chart = chartsCreated[0];
    expect(chart.candleSeries.createPriceLine).toHaveBeenCalledTimes(2);
    expect(chart.candleSeries.createPriceLine).toHaveBeenCalledWith(
      expect.objectContaining({ price: 26.46, title: "وقف الخسارة", color: "red" })
    );
    expect(chart.candleSeries.createPriceLine).toHaveBeenCalledWith(
      expect.objectContaining({ price: 27.7, title: "الهدف الأول", color: "green" })
    );
  });

  it("draws no price lines when no levels are provided", () => {
    render(<PriceChart bars={BARS} />);
    const chart = chartsCreated[0];
    expect(chart.candleSeries.createPriceLine).not.toHaveBeenCalled();
  });

  it("removes the old price lines when the levels prop changes", () => {
    const { rerender } = render(
      <PriceChart bars={BARS} levels={[{ price: 26.46, label: "وقف الخسارة", color: "red" }]} />
    );
    const chart = chartsCreated[0];
    expect(chart.candleSeries.createPriceLine).toHaveBeenCalledTimes(1);

    rerender(<PriceChart bars={BARS} levels={[{ price: 27.7, label: "الهدف الأول", color: "green" }]} />);
    expect(chart.candleSeries.removePriceLine).toHaveBeenCalledTimes(1);
    expect(chart.candleSeries.createPriceLine).toHaveBeenCalledTimes(2);
  });

  it("removes the underlying chart instance on unmount, so switching symbols never leaks a chart", () => {
    const { unmount } = render(<PriceChart bars={BARS} />);
    const chart = chartsCreated[0];
    unmount();
    expect(chart.remove).toHaveBeenCalledTimes(1);
  });

  const SMA_POINTS: MovingAveragePoint[] = [
    { timestamp: "2026-08-03T00:00:00Z", value: 26.8 },
    { timestamp: "2026-08-04T00:00:00Z", value: 27.0 },
  ];

  it("draws one line series per moving-average overlay, with the caller's own label/color", () => {
    render(
      <PriceChart
        bars={BARS}
        movingAverages={[{ name: "sma_20", label: "المتوسط المتحرك البسيط (20)", color: "#3E8ED0", points: SMA_POINTS }]}
      />
    );
    const chart = chartsCreated[0];
    expect(chart.lineSeriesCreated).toHaveLength(1);
    expect(chart.addSeries).toHaveBeenCalledWith(
      "LineSeriesMarker",
      expect.objectContaining({ color: "#3E8ED0", title: "المتوسط المتحرك البسيط (20)" })
    );
    expect(chart.lineSeriesCreated[0].setData).toHaveBeenCalledWith([
      { time: expect.any(Number), value: 26.8 },
      { time: expect.any(Number), value: 27.0 },
    ]);
  });

  it("draws no line series when no moving averages are provided", () => {
    render(<PriceChart bars={BARS} />);
    const chart = chartsCreated[0];
    expect(chart.lineSeriesCreated).toHaveLength(0);
  });

  it("removes the old line series when the movingAverages prop changes", () => {
    const { rerender } = render(
      <PriceChart bars={BARS} movingAverages={[{ name: "sma_20", label: "SMA", color: "#3E8ED0", points: SMA_POINTS }]} />
    );
    const chart = chartsCreated[0];
    expect(chart.lineSeriesCreated).toHaveLength(1);

    rerender(
      <PriceChart
        bars={BARS}
        movingAverages={[
          { name: "sma_20", label: "SMA", color: "#3E8ED0", points: SMA_POINTS },
          { name: "ema_20", label: "EMA", color: "#C9A24B", points: SMA_POINTS },
        ]}
      />
    );
    expect(chart.removeSeries).toHaveBeenCalledTimes(1);
    expect(chart.lineSeriesCreated).toHaveLength(3);
  });

  it("still draws a (empty) line series when an overlay's points array is empty, without crashing", () => {
    /** Phase 2I: a real indicator can be entirely undefined over the
     * whole window (e.g. vwap_20 with all-zero volume) -- the backend
     * then sends an empty points array rather than omitting the key.
     * The chart must render that as a real, present-but-empty series,
     * not silently drop the overlay or throw. */
    render(
      <PriceChart
        bars={BARS}
        movingAverages={[{ name: "vwap_20", label: "VWAP (20)", color: "#8A63D2", points: [] }]}
      />
    );
    const chart = chartsCreated[0];
    expect(chart.lineSeriesCreated).toHaveLength(1);
    expect(chart.lineSeriesCreated[0].setData).toHaveBeenCalledWith([]);
  });
});
