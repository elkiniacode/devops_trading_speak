import type { Candle } from "./types";

export function sma(values: number[], period: number): Array<number | null> {
  let sum = 0;
  return values.map((value, index) => {
    sum += value;
    if (index >= period) sum -= values[index - period];
    return index < period - 1 ? null : sum / period;
  });
}

export function ema(values: number[], period: number): Array<number | null> {
  const output: Array<number | null> = [];
  const multiplier = 2 / (period + 1);
  let previous = 0;
  let warmup = 0;
  values.forEach((value, index) => {
    if (index < period) {
      warmup += value;
      if (index === period - 1) previous = warmup / period;
      output.push(index === period - 1 ? previous : null);
    } else {
      previous = value * multiplier + previous * (1 - multiplier);
      output.push(previous);
    }
  });
  return output;
}

export function rsi(values: number[], period = 14): Array<number | null> {
  const result: Array<number | null> = Array(values.length).fill(null);
  if (values.length <= period) return result;
  let gains = 0;
  let losses = 0;
  for (let i = 1; i <= period; i++) {
    const change = values[i] - values[i - 1];
    gains += Math.max(0, change);
    losses += Math.max(0, -change);
  }
  gains /= period;
  losses /= period;
  result[period] = losses === 0 ? 100 : 100 - 100 / (1 + gains / losses);
  for (let i = period + 1; i < values.length; i++) {
    const change = values[i] - values[i - 1];
    gains = (gains * (period - 1) + Math.max(0, change)) / period;
    losses = (losses * (period - 1) + Math.max(0, -change)) / period;
    result[i] = losses === 0 ? 100 : 100 - 100 / (1 + gains / losses);
  }
  return result;
}

export function macd(values: number[]): { line: Array<number | null>; signal: Array<number | null>; histogram: Array<number | null> } {
  const fast = ema(values, 12);
  const slow = ema(values, 26);
  const line = values.map((_, index) => fast[index] === null || slow[index] === null ? null : fast[index]! - slow[index]!);
  const compact = line.filter((value): value is number => value !== null);
  const signalValues = ema(compact, 9);
  let cursor = 0;
  const signal = line.map((value) => value === null ? null : signalValues[cursor++]);
  return { line, signal, histogram: line.map((value, index) => value === null || signal[index] === null ? null : value - signal[index]!) };
}

export function atr(candles: Candle[], period = 14): number {
  if (candles.length < 2) return 0;
  const ranges = candles.slice(1).map((candle, index) => Math.max(
    candle.high - candle.low,
    Math.abs(candle.high - candles[index].close),
    Math.abs(candle.low - candles[index].close),
  ));
  const sample = ranges.slice(-period);
  return sample.reduce((sum, value) => sum + value, 0) / sample.length;
}
