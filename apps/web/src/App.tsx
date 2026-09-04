import { BrowserRouter, Route, Routes } from "react-router-dom";
import { AuthProvider, RequireAuth } from "./auth/AuthProvider";
import { AppShell } from "./components/AppShell";
import { AuditPage } from "./pages/AuditPage";
import { ActionsPage } from "./pages/ActionsPage";
import { ApprovalsPage } from "./pages/ApprovalsPage";
import { PoliciesPage } from "./pages/PoliciesPage";
import { LoginPage } from "./pages/LoginPage";
import { FileGovernancePage } from "./pages/FileGovernancePage";
import { RunDetailPage } from "./pages/RunDetailPage";
import { RunsPage } from "./pages/RunsPage";
import { SystemPage } from "./pages/SystemPage";
import { TargetsPage } from "./pages/TargetsPage";
import { WorkspacesPage } from "./pages/WorkspacesPage";

function App() {
  return (
    <BrowserRouter>
      <AuthProvider>
        <Routes>
          <Route path="login" element={<LoginPage />} />
          <Route element={<RequireAuth><AppShell /></RequireAuth>}>
            <Route index element={<RunsPage />} />
            <Route path="files" element={<FileGovernancePage />} />
            <Route path="actions" element={<ActionsPage />} />
            <Route path="approvals" element={<ApprovalsPage />} />
            <Route path="workspaces" element={<WorkspacesPage />} />
            <Route path="system" element={<SystemPage />} />
            <Route path="runs/:runId" element={<RunDetailPage />} />
            <Route path="policies" element={<PoliciesPage />} />
            <Route path="audit" element={<AuditPage />} />
            <Route path="monitor" element={<TargetsPage />} />
          </Route>
        </Routes>
      </AuthProvider>
    </BrowserRouter>
  );
}

export default App;
