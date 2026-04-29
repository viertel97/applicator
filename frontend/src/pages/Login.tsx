export default function Login() {
  return (
    <div className="min-h-screen flex items-center justify-center bg-slate-50">
      <div className="bg-white p-8 rounded shadow w-96 text-center">
        <h1 className="text-2xl font-semibold mb-6">Applicator</h1>
        <a
          href="/api/auth/login"
          className="inline-block bg-blue-600 text-white px-6 py-2 rounded hover:bg-blue-700"
        >
          Sign in with Microsoft
        </a>
      </div>
    </div>
  );
}
