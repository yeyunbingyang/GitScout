interface ProjectRankBadgeProps { rank: number; className?: string; }
const medalAssets: Record<number, { file: string; label: string }> = {
  1: { file: "crown-gold.svg", label: "第一名" },
  2: { file: "crown-silver.svg", label: "第二名" },
  3: { file: "crown-bronze.svg", label: "第三名" },
};
export default function ProjectRankBadge({ rank, className = "" }: ProjectRankBadgeProps) {
  const medal = medalAssets[rank];
  return <span className={["project-rank-badge", medal ? "has-medal" : "is-number", className].filter(Boolean).join(" ")}
    aria-label={medal?.label ?? "排名 " + rank}>{medal ? <img src={"/assets/gitscout/" + medal.file} alt="" /> : rank}</span>;
}
