interface Props {
  title: string;
  description: string;
  milestone: string;
}

export default function PlaceholderPage({ title, description, milestone }: Props) {
  return (
    <div className="page-stack">
      <section className="surface-card placeholder-panel">
        <span className="eyebrow">{milestone}</span>
        <h2>{title}</h2>
        <p>{description}</p>
        <div className="notice-line">页面入口已建立 · 功能将在对应开发阶段接入真实 API</div>
      </section>
    </div>
  );
}
