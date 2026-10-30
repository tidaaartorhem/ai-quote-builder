import { useEffect, useState } from "react";
import type { PricebookEntry, QuoteRow, Summary, TestVectors } from "./types";

export interface QuoteDeskData {
  summary: Summary;
  quotes: QuoteRow[];
  pricebook: PricebookEntry[];
  vectors: TestVectors;
}

async function get<T>(name: string): Promise<T> {
  const res = await fetch(`data/${name}.json`);
  if (!res.ok) throw new Error(`failed to load data/${name}.json`);
  return res.json() as Promise<T>;
}

/** Loads the pipeline payloads (written by scripts/build_quotedesk.py). */
export function useQuoteDeskData() {
  const [data, setData] = useState<QuoteDeskData | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    (async () => {
      try {
        const [summary, quotes, pricebook, vectors] = await Promise.all([
          get<Summary>("summary"),
          get<QuoteRow[]>("quotes"),
          get<PricebookEntry[]>("pricebook"),
          get<TestVectors>("test-vectors"),
        ]);
        setData({ summary, quotes, pricebook, vectors });
      } catch (e) {
        setError(e instanceof Error ? e.message : String(e));
      }
    })();
  }, []);

  return { data, error };
}

export function fmtMoney(cents: number): string {
  return "$" + (cents / 100).toFixed(2);
}
