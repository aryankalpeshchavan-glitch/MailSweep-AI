import { useCallback, useEffect, useMemo, type ReactNode } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { authKeys, useAuthStatus } from "@/api/queries";
import { postLogout } from "@/api/endpoints";
import { SESSION_EXPIRED_EVENT } from "@/lib/apiClient";
import { AuthContext, type AuthCtx } from "@/context/auth-context";

export function AuthProvider({ children }: { children: ReactNode }) {
  const { data: status, isError } = useAuthStatus();
  const queryClient = useQueryClient();

  const logoutMutation = useMutation({
    mutationFn: postLogout,
    onSuccess: () => queryClient.removeQueries(),
  });

  // Session expiry/revoke anywhere => drop cached data + refetch status.
  useEffect(() => {
    const handle = () => queryClient.removeQueries();
    window.addEventListener(SESSION_EXPIRED_EVENT, handle);
    return () => window.removeEventListener(SESSION_EXPIRED_EVENT, handle);
  }, [queryClient]);

  const logout = useCallback(async () => {
    try {
      await logoutMutation.mutateAsync();
    } finally {
      queryClient.removeQueries();
      await queryClient.invalidateQueries({ queryKey: authKeys.all });
    }
  }, [logoutMutation, queryClient]);

  const value = useMemo<AuthCtx>(() => {
    const authenticated = Boolean(status?.authenticated);
    return {
      status,
      isAuthenticated: authenticated,
      // treat an error as "not signed in" (server unreachable → guest view),
      isLoading: status === undefined && !isError,
      displayName: status?.user?.display_name ?? status?.user?.email ?? null,
      logout,
      gmailConnected: Boolean(status?.gmail_connection?.connected),
    };
  }, [status, isError, logout]);

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

