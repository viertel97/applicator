export default function SettingsLLM() {
  return (
    <div className="max-w-2xl mx-auto p-6 prose">
      <h1>LLM settings</h1>
      <p>
        LLM provider, model, base URL and API key are configured via the backend{" "}
        <code>.env</code> for MVP. Defaults: <code>LLM_PROVIDER=groq</code>,{" "}
        <code>LLM_MODEL=gpt-oss</code>,{" "}
        <code>LLM_BASE_URL=https://api.groq.com/openai/v1</code>.
      </p>
    </div>
  );
}
