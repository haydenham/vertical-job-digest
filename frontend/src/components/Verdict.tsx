import type { Verdict } from "../api";

const LABELS: Record<Verdict, string> = {
  strong_yes: "strong",
  yes: "yes",
  maybe: "maybe",
  no: "no",
};

// Verdict badge + mono score, color-coded by verdict strength (DESIGN.md: numbers big in mono,
// one accent hue). `null` verdict = in-scope but unassessed → a dim em-dash, never a fake score.
export function MatchCell({
  verdict,
  score,
}: {
  verdict: Verdict | null;
  score: number | null;
}) {
  if (verdict === null) {
    return <span className="match-none">—</span>;
  }
  return (
    <span className="match">
      <span className={`verdict verdict-${verdict}`}>{LABELS[verdict]}</span>
      {score !== null && <span className={`score score-${verdict}`}>{score}</span>}
    </span>
  );
}
