export default function AgentGraph() {
  const agents = [
    "Planner",
    "Retriever",
    "LLM",
    "Evaluation",
    "Governance",
    "Security",
    "Council",
    "Human Approval"
  ];

  return (
    <section style={{ border: "1px solid #ccc", padding: "16px" }}>
      <h2>Agent Graph</h2>

      {agents.map((agent, index) => (
        <div key={agent}>
          <strong>{agent}</strong>
          {index < agents.length - 1 && <span> → </span>}
        </div>
      ))}
    </section>
  );
}
