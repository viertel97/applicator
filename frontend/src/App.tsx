import { Link, Navigate, Route, Routes, useLocation } from "react-router-dom";
import Login from "./pages/Login";
import ApplicationsList from "./pages/ApplicationsList";
import ApplicationDetail from "./pages/ApplicationDetail";
import SettingsCV from "./pages/SettingsCV";
import SettingsAnschreiben from "./pages/SettingsAnschreiben";
import SettingsLLM from "./pages/SettingsLLM";
import { useAuth } from "./hooks/useAuth";

function Nav() {
  const loc = useLocation();
  const { data: authData } = useAuth();
  const item = (to: string, label: string) => (
    <Link
      key={to}
      to={to}
      className={`px-3 py-2 ${loc.pathname.startsWith(to) ? "font-semibold" : ""}`}
    >
      {label}
    </Link>
  );
  return (
    <nav className="bg-white border-b px-4 py-2 flex gap-2 items-center">
      <span className="font-bold mr-3">Applicator</span>
      {item("/applications", "Applications")}
      {item("/settings/cv", "CV")}
      {item("/settings/anschreiben", "Anschreiben")}
      {item("/settings/llm", "LLM")}
      {authData?.oauth_enabled && (
        <form action="/api/auth/logout" method="post" className="ml-auto">
          <button className="text-sm text-slate-600">Logout</button>
        </form>
      )}
    </nav>
  );
}

function ProtectedShell({ children }: { children: React.ReactNode }) {
  const { data, isLoading } = useAuth();
  if (isLoading) return <div className="p-6">Loading…</div>;
  if (!data) return <Navigate to="/login" replace />;
  return (
    <>
      <Nav />
      {children}
    </>
  );
}

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<Login />} />
      <Route
        path="/applications"
        element={
          <ProtectedShell>
            <ApplicationsList />
          </ProtectedShell>
        }
      />
      <Route
        path="/applications/:id"
        element={
          <ProtectedShell>
            <ApplicationDetail />
          </ProtectedShell>
        }
      />
      <Route
        path="/settings/cv"
        element={
          <ProtectedShell>
            <SettingsCV />
          </ProtectedShell>
        }
      />
      <Route
        path="/settings/anschreiben"
        element={
          <ProtectedShell>
            <SettingsAnschreiben />
          </ProtectedShell>
        }
      />
      <Route
        path="/settings/llm"
        element={
          <ProtectedShell>
            <SettingsLLM />
          </ProtectedShell>
        }
      />
      <Route path="*" element={<Navigate to="/applications" replace />} />
    </Routes>
  );
}
