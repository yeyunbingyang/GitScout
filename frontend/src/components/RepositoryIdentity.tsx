import type { ReactNode } from "react";
import { Link } from "react-router-dom";
export type RepositoryIdentityVariant = "table" | "compact" | "card" | "hero";
export interface RepositoryIdentityProps {
  fullName: string; owner?: string; name?: string; description?: string | null;
  to?: string; variant?: RepositoryIdentityVariant; meta?: ReactNode; className?: string;
}
export default function RepositoryIdentity({ fullName, owner, name, description, to, variant = "table", meta, className = "" }: RepositoryIdentityProps) {
  const separator = fullName.indexOf("/");
  const displayOwner = owner ?? (separator >= 0 ? fullName.slice(0, separator) : "");
  const displayName = name ?? (separator >= 0 ? fullName.slice(separator + 1) : fullName);
  const title = to ? <Link className="repository-identity-title" to={to}>{displayName}</Link> : <strong className="repository-identity-title">{displayName}</strong>;
  return <div className={["repository-identity", "repository-identity--" + variant, className].filter(Boolean).join(" ")}>
    <span className="repository-identity-accent" aria-hidden="true" />
    <div className="repository-identity-content">
      {displayOwner && <span className="repository-identity-owner">{displayOwner}</span>}
      {title}
      {description && <p className="repository-identity-description">{description}</p>}
      {meta && <div className="repository-identity-meta">{meta}</div>}
    </div>
  </div>;
}
