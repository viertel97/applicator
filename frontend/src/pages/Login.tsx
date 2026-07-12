import { useEffect, useState } from "react";

export default function Login() {
  const [oauthEnabled, setOauthEnabled] = useState<boolean | null>(null);

  useEffect(() => {
    fetch("/api/auth/mode")
      .then((r) => r.json())
      .then((d) => setOauthEnabled(d.oauth_enabled))
      .catch(() => setOauthEnabled(true));
  }, []);

  return (
    <div className="min-h-screen flex items-center justify-center bg-bg">
      <div className="bg-surface p-8 rounded shadow w-96 text-center">
        <h1 className="text-2xl font-semibold mb-6">Applicator</h1>
        {oauthEnabled === null ? null : oauthEnabled ? (
          <a
            href="/api/auth/login"
            className="inline-block bg-accent text-accentFg px-6 py-2 rounded hover:opacity-90"
          >
            Sign in with Microsoft
          </a>
        ) : (
          <a
            href="/api/auth/login"
            className="inline-block bg-surface2 text-fg px-6 py-2 rounded hover:opacity-90"
          >
            Continue (unsecured mode)
          </a>
        )}
      </div>
    </div>
  );
}
