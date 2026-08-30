export function EmptyState({ title, description }: { title: string; description: string }) {
  return (
    <div className="empty-state">
      <span className="empty-kicker">No records yet</span>
      <h2>{title}</h2>
      <p>{description}</p>
    </div>
  );
}
