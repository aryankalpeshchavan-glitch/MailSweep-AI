import { createContext } from "react";
import type { AuthStatus } from "@/types/api";

export interface AuthCtx {
  /** undefined while the initial status query is in flight. */
  status: AuthStatus | undefined;
  isAuthenticated: boolean;
  isLoading: boolean;
  /** currently signed-in display name (for the shell). */
  displayName: string | null;
  /** revoke the session cookie server-side + clear local state. */
  logout: () => Promise<void>;
  /** is the Google/Gmail account currently connected. */
  gmailConnected: boolean;
}

export const AuthContext = createContext<AuthCtx | null>(null);
