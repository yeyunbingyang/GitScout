import { useEffect, useState } from "react";
import { Bookmark, BookmarkCheck, BookOpen, Plus, LoaderCircle } from "lucide-react";
import { Link } from "react-router-dom";
import { api, type ResearchStatus } from "../services/api";

interface RepositoryWorkspaceActionsProps {
  repositoryId: number;
  interested: boolean;
  researchStatus: ResearchStatus | null;
  sourcePage: string;
  compact?: boolean;
}

export default function RepositoryWorkspaceActions({
  repositoryId,
  interested,
  researchStatus,
  sourcePage,
  compact = false,
}: RepositoryWorkspaceActionsProps) {
  const [isInterested, setIsInterested] = useState(interested);
  const [currentResearchStatus, setCurrentResearchStatus] = useState<ResearchStatus | null>(researchStatus);
  const [busy, setBusy] = useState<"interest" | "research" | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setIsInterested(interested);
    setCurrentResearchStatus(researchStatus);
  }, [interested, researchStatus]);

  async function toggleInterest() {
    setBusy("interest");
    setError(null);
    try {
      if (isInterested) {
        await api.removeInterested(repositoryId);
        setIsInterested(false);
      } else {
        await api.markInterested({ repository_id: repositoryId, source_page: sourcePage });
        setIsInterested(true);
      }
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "更新兴趣标记失败");
    } finally {
      setBusy(null);
    }
  }

  async function addResearch() {
    setBusy("research");
    setError(null);
    try {
      await api.createResearchProject({ repository_id: repositoryId });
      setCurrentResearchStatus("pending");
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "加入研究工作区失败");
    } finally {
      setBusy(null);
    }
  }

  return (
    <div className={"repository-workspace-actions" + (compact ? " compact" : "")}>
      <button className={isInterested ? "button button-workspace-active" : "button button-quiet"}
        disabled={busy !== null} onClick={() => void toggleInterest()}>
        {busy === "interest" ? <LoaderCircle size={13} className="spin" /> : isInterested ? <BookmarkCheck size={13} /> : <Bookmark size={13} />}
        {isInterested ? "已感兴趣" : "标记感兴趣"}
      </button>
      {currentResearchStatus ? (
        <Link className="button button-workspace-active" to="/research">
          <BookOpen size={13} />{currentResearchStatus === "completed" ? "已完成研究" : "已加入研究"}
        </Link>
      ) : (
        <button className="button button-quiet" disabled={busy !== null} onClick={() => void addResearch()}>
          {busy === "research" ? <LoaderCircle size={13} className="spin" /> : <Plus size={13} />}
          加入研究
        </button>
      )}
      {error && <span className="workspace-action-error">{error}</span>}
    </div>
  );
}
