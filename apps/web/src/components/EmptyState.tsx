export function EmptyState({ title, description }: { title: string; description: string }) {
  return (
    <div className="empty-state">
      <span className="empty-kicker">暂无记录</span>
      <h2>{title}</h2>
      <p>{description}</p>
    </div>
  );
}
