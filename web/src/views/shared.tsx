import { TIER_LABEL } from "../rules";

const TIER_CLASS: Record<string, string> = {
  AUTO: "ok",
  REVIEW: "warn",
  MANUAL: "bad",
};

export function TierBadge({ tier }: { tier: string }) {
  return (
    <span className={`pill ${TIER_CLASS[tier] ?? "neutral"}`}>
      {TIER_LABEL[tier] ?? tier}
    </span>
  );
}

export function MatchBar({ value }: { value: number }) {
  return (
    <span className="confbar">
      <span className="confbar-track">
        <span className="confbar-fill" style={{ width: `${Math.min(100, value)}%` }} />
      </span>
      <span className="confbar-num mono">{value.toFixed(1)}</span>
    </span>
  );
}

export function ReviewFlag() {
  return <span className="pill bad">needs review</span>;
}
