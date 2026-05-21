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
    <div className="min-h-screen flex items-center justify-center bg-slate-50">
      <div className="bg-white p-8 rounded shadow w-96 text-center">
        <h1 className="text-2xl font-semibold mb-6">Applicator</h1>
        {oauthEnabled === null ? null : oauthEnabled ? (
          <a
            href="/api/auth/login"
            className="inline-block bg-blue-600 text-white px-6 py-2 rounded hover:bg-blue-700"
          >
            Sign in with Microsoft
          </a>
        ) : (
          <a
            href="/api/auth/login"
            className="inline-block bg-slate-700 text-white px-6 py-2 rounded hover:bg-slate-800"
          >
            Continue (unsecured mode)
          </a>
        )}
      </div>
    </div>
  );
}
