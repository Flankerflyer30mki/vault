import { useEffect, useRef, useState } from "react";
import { errorText } from "./api";
import { useAuth } from "./auth";

// "Sign in with Google" (D-103). Google's own button (Google Identity Services) hands us a signed ID token; the
// server verifies it and signs us in with the usual session cookie. Hidden unless the server reports a client ID.
const GSI_SRC = "https://accounts.google.com/gsi/client";
let loading = null;

function loadGoogle() {
  if (window.google?.accounts?.id) return Promise.resolve(window.google);
  if (!loading) {
    loading = new Promise((resolve, reject) => {
      const script = document.createElement("script");
      script.src = GSI_SRC;
      script.async = true;
      script.onload = () => resolve(window.google);
      script.onerror = () => {
        loading = null;
        reject(new Error("Couldn't load Google sign-in."));
      };
      document.head.appendChild(script);
    });
  }
  return loading;
}

export default function GoogleButton({ text = "signin_with", onDone }) {
  const { googleClientId, google } = useAuth();
  const box = useRef(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  // Google keeps the callback it was initialised with, so it reads the latest handlers through a ref.
  const handlers = useRef({ google, onDone });
  useEffect(() => {
    handlers.current = { google, onDone };
  }, [google, onDone]);

  useEffect(() => {
    if (!googleClientId) return undefined;
    let cancelled = false;
    loadGoogle()
      .then((g) => {
        if (cancelled || !box.current) return;
        g.accounts.id.initialize({
          client_id: googleClientId,
          callback: ({ credential }) => {
            setBusy(true);
            setError("");
            handlers.current
              .google(credential)
              .then(() => handlers.current.onDone?.())
              .catch((err) => setError(errorText(err)))
              .finally(() => setBusy(false));
          },
        });
        g.accounts.id.renderButton(box.current, {
          theme: "outline",
          size: "large",
          text,
          shape: "rectangular",
        });
      })
      .catch((err) => setError(err.message));
    return () => {
      cancelled = true;
    };
  }, [googleClientId, text]);

  if (!googleClientId) return null;
  return (
    <div className="google-box">
      <div ref={box} data-testid="google-button" aria-busy={busy} />
      {busy && <p className="hint">Signing in…</p>}
      {error && <p className="error">{error}</p>}
    </div>
  );
}
