import { Navigate, Route, Routes } from "react-router-dom";
import Login from "./pages/Login";
import ApplicationsList from "./pages/ApplicationsList";
import ApplicationDetail from "./pages/ApplicationDetail";
import Suggestions from "./pages/Suggestions";
import SettingsCV from "./pages/SettingsCV";
import SettingsAnschreiben from "./pages/SettingsAnschreiben";
import SettingsLLM from "./pages/SettingsLLM";
import SettingsInquiryPrompt from "./pages/SettingsInquiryPrompt";
import SettingsDiscardReasons from "./pages/SettingsDiscardReasons";
import Stats from "./pages/Stats";
import { useAuth } from "./hooks/useAuth";
import { DesktopNav } from "./components/nav/DesktopNav";
import { MobileNav } from "./components/nav/MobileNav";

function ProtectedShell({ children }: { children: React.ReactNode }) {
  const { data, isLoading } = useAuth();
  if (isLoading) return <div className="p-6 text-muted">Loading…</div>;
  if (!data) return <Navigate to="/login" replace />;
  return (
    <>
      <DesktopNav oauthEnabled={data.oauth_enabled} />
      <MobileNav oauthEnabled={data.oauth_enabled} />
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
        path="/suggestions"
        element={
          <ProtectedShell>
            <Suggestions />
          </ProtectedShell>
        }
      />
      <Route
        path="/stats"
        element={
          <ProtectedShell>
            <Stats />
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
      <Route
        path="/settings/inquiry-prompt"
        element={
          <ProtectedShell>
            <SettingsInquiryPrompt />
          </ProtectedShell>
        }
      />
      <Route
        path="/settings/discard-reasons"
        element={
          <ProtectedShell>
            <SettingsDiscardReasons />
          </ProtectedShell>
        }
      />
      <Route path="*" element={<Navigate to="/applications" replace />} />
    </Routes>
  );
}
