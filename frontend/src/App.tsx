import { Navigate, Route, Routes } from "react-router-dom";
import type { ReactNode } from "react";
import { useAuth } from "@/context/AuthContext";
import { AuthenticatedLayout } from "@/layouts/AuthenticatedLayout";
import { PublicLayout } from "@/layouts/PublicLayout";
import { MailUniversePage } from "@/pages/LandingPage";
import { DashboardPage } from "@/pages/DashboardPage";
import { RecommendationsPage } from "@/pages/RecommendationsPage";
import { AnalysisApprovalPage } from "@/pages/AnalysisApprovalPage";
import { LoginPage } from "@/pages/LoginPage";
import { NotFoundPage } from "@/pages/NotFoundPage";
import { LoadingBlock } from "@/components/ui";

/** Guests can't reach authenticated routes; signed-in users are sent home. */
export function RequireAuth({ children }: { children: ReactNode }) {
  const { isAuthenticated, isLoading } = useAuth();
  if (isLoading) return <LoadingBlock label="Verifying session" />;
  if (!isAuthenticated) return <Navigate to="/login" replace />;
  return <>{children}</>;
}

function GuestOnly({ children }: { children: ReactNode }) {
  const { isAuthenticated, isLoading } = useAuth();
  if (isLoading) return <LoadingBlock label="Checking session" />;
  if (isAuthenticated) return <Navigate to="/dashboard" replace />;
  return <>{children}</>;
}

export function App() {
  return (
    <Routes>
      {/* Public: cinematic landing + login */}
      <Route element={<PublicLayout />}>
        <Route index element={<MailUniversePage />} />
        <Route
          path="login"
          element={
            <GuestOnly>
              <LoginPage />
            </GuestOnly>
          }
        />
      </Route>

      {/* Authenticated app */}
      <Route
        path="/dashboard"
        element={
          <RequireAuth>
            <AuthenticatedLayout>
              <DashboardPage />
            </AuthenticatedLayout>
          </RequireAuth>
        }
      />
      <Route
        path="/recommendations"
        element={
          <RequireAuth>
            <AuthenticatedLayout>
              <RecommendationsPage />
            </AuthenticatedLayout>
          </RequireAuth>
        }
      />
      <Route
        path="/analysis"
        element={
          <RequireAuth>
            <AuthenticatedLayout>
              <AnalysisApprovalPage />
            </AuthenticatedLayout>
          </RequireAuth>
        }
      />

      <Route path="*" element={<NotFoundPage />} />
    </Routes>
  );
}