import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import { Navigate, useLocation } from "react-router-dom";
import api, { UNAUTHENTICATED } from "./api";

const AuthContext = createContext(null);

// Holds the signed-in user. The session itself lives in an HttpOnly cookie that JavaScript never sees;
// this only mirrors what /api/auth/me/ says.
export function AuthProvider({ children }) {
  const [user, setUser] = useState(undefined); // undefined = still loading, null = signed out
  const [googleClientId, setGoogleClientId] = useState(""); // "" = Sign in with Google is off

  const refresh = useCallback(
    () =>
      api
        .get("/auth/me/") // also sets the csrftoken cookie
        .then((res) => {
          setUser(res.data.user);
          setGoogleClientId(res.data.google_client_id || "");
        })
        .catch(() => setUser(null)),
    [],
  );

  useEffect(() => {
    refresh();
    const onUnauthenticated = () => setUser(null);
    window.addEventListener(UNAUTHENTICATED, onUnauthenticated);
    return () => window.removeEventListener(UNAUTHENTICATED, onUnauthenticated);
  }, [refresh]);

  const value = useMemo(
    () => ({
      user,
      setUser,
      googleClientId,
      refresh,
      login: (email, password) => api.post("/auth/login/", { email, password }).then((r) => setUser(r.data.user)),
      signup: (email, password, display_name) =>
        api.post("/auth/signup/", { email, password, display_name }).then((r) => setUser(r.data.user)),
      guest: () => api.post("/auth/guest/").then((r) => setUser(r.data.user)),
      google: (credential) => api.post("/auth/google/", { credential }).then((r) => setUser(r.data.user)),
      logout: () => api.post("/auth/logout/").finally(() => setUser(null)),
    }),
    [user, googleClientId, refresh],
  );
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

// eslint-disable-next-line react-refresh/only-export-components
export function useAuth() {
  return useContext(AuthContext);
}

export function RequireAuth({ children }) {
  const { user } = useAuth();
  const location = useLocation();
  if (user === undefined) return <p>Loading…</p>;
  if (!user) return <Navigate to="/login" replace state={{ from: location.pathname }} />;
  return children;
}

export function GuestOnly({ children }) {
  const { user } = useAuth();
  if (user === undefined) return <p>Loading…</p>;
  if (user) return <Navigate to="/" replace />;
  return children;
}
