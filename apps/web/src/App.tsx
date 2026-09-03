import { BrowserRouter, Route, Routes } from "react-router-dom";
import { AuthProvider, RequireAuth } from "./auth/AuthProvider";
import { AppShell } from "./components/AppShell";
import { AuditPage } from "./pages/AuditPage";
import { PoliciesPage } from "./pages/PoliciesPage";
import { LoginPage } from "./pages/LoginPage";
import { RunDetailPage } from "./pages/RunDetailPage";
import { RunsPage } from "./pages/RunsPage";
import { TargetsPage } from "./pages/TargetsPage";

function App() {
  return (
    <BrowserRouter>
      <AuthProvider>
        <Routes>
          <Route path="login" element={<LoginPage />} />
          <Route element={<RequireAuth><AppShell /></RequireAuth>}>
            <Route index element={<RunsPage />} />
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
