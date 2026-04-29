import { Navigate, Route, Routes } from "react-router-dom";
import Login from "./pages/Login";
import ApplicationsList from "./pages/ApplicationsList";
import ApplicationDetail from "./pages/ApplicationDetail";
import { useAuth } from "./hooks/useAuth";

function ProtectedShell({ children }: { children: React.ReactNode }) {
  const { data, isLoading } = useAuth();
  if (isLoading) return <div className="p-6">Loading…</div>;
  if (!data) return <Navigate to="/login" replace />;
  return <>{children}</>;
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
      <Route path="*" element={<Navigate to="/applications" replace />} />
    </Routes>
  );
}
