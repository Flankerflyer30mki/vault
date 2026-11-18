import { useEffect, useRef, useState } from "react";
import { Link, useLocation, useNavigate, useSearchParams } from "react-router-dom";
import api, { errorText } from "../api";
import { useAuth } from "../auth";
import GoogleButton from "../GoogleButton";

function GuestButton() {
  const { guest } = useAuth();
  const navigate = useNavigate();
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const start = () => {
    setBusy(true);
    setError("");
    guest()
      .then(() => navigate("/"))
      .catch((err) => setError(errorText(err)))
      .finally(() => setBusy(false));
  };
  return (
    <div className="guest-box">
      <button type="button" className="secondary" onClick={start} disabled={busy}>
        {busy ? "Starting…" : "Try it as a guest"}
      </button>
      <p className="hint">No sign-up. Guest workspaces are deleted after 7 days unless you save them as an account.</p>
      {error && <p className="error">{error}</p>}
    </div>
  );
}

export function Login() {
  const { login } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  const submit = (e) => {
    e.preventDefault();
    setBusy(true);
    setError("");
    login(email, password)
      .then(() => navigate(location.state?.from || "/", { replace: true }))
      .catch((err) => setError(errorText(err)))
      .finally(() => setBusy(false));
  };

  return (
    <div className="auth-card">
      <h1>Sign in</h1>
      <GoogleButton onDone={() => navigate(location.state?.from || "/", { replace: true })} />
      <form onSubmit={submit} className="auth-form">
        <label>
          Email
          <input type="email" autoComplete="email" value={email} onChange={(e) => setEmail(e.target.value)} required />
        </label>
        <label>
          Password
          <input
            type="password"
            autoComplete="current-password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            required
          />
        </label>
        {error && <p className="error pre">{error}</p>}
        <button type="submit" disabled={busy}>
          {busy ? "Signing in…" : "Sign in"}
        </button>
      </form>
      <p className="auth-links">
        <Link to="/forgot-password">Forgot password?</Link> · <Link to="/signup">Create an account</Link>
      </p>
      <GuestButton />
    </div>
  );
}

export function Signup() {
  const { signup } = useAuth();
  const navigate = useNavigate();
  const [form, setForm] = useState({ email: "", password: "", display_name: "" });
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const set = (k) => (e) => setForm({ ...form, [k]: e.target.value });

  const submit = (e) => {
    e.preventDefault();
    setBusy(true);
    setError("");
    signup(form.email, form.password, form.display_name)
      .then(() => navigate("/", { replace: true }))
      .catch((err) => setError(errorText(err)))
      .finally(() => setBusy(false));
  };

  return (
    <div className="auth-card">
      <h1>Create an account</h1>
      <GoogleButton text="signup_with" onDone={() => navigate("/", { replace: true })} />
      <form onSubmit={submit} className="auth-form">
        <label>
          Name (optional)
          <input type="text" maxLength={100} value={form.display_name} onChange={set("display_name")} />
        </label>
        <label>
          Email
          <input type="email" autoComplete="email" value={form.email} onChange={set("email")} required />
        </label>
        <label>
          Password (at least 10 characters, not a common password)
          <input
            type="password"
            autoComplete="new-password"
            minLength={10}
            value={form.password}
            onChange={set("password")}
            required
          />
        </label>
        {error && <p className="error pre">{error}</p>}
        <button type="submit" disabled={busy}>
          {busy ? "Creating…" : "Create account"}
        </button>
      </form>
      <p className="hint">We&apos;ll email you a link to verify your address. Verified accounts get higher limits.</p>
      <p className="auth-links">
        Already have an account? <Link to="/login">Sign in</Link>
      </p>
      <GuestButton />
    </div>
  );
}

export function ForgotPassword() {
  const [email, setEmail] = useState("");
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const submit = (e) => {
    e.preventDefault();
    setError("");
    api
      .post("/auth/password-reset/", { email })
      .then((res) => setMessage(res.data.detail))
      .catch((err) => setError(errorText(err)));
  };
  return (
    <div className="auth-card">
      <h1>Reset your password</h1>
      {message ? (
        <p className="success">{message}</p>
      ) : (
        <form onSubmit={submit} className="auth-form">
          <label>
            Email
            <input type="email" value={email} onChange={(e) => setEmail(e.target.value)} required />
          </label>
          {error && <p className="error pre">{error}</p>}
          <button type="submit">Send reset link</button>
        </form>
      )}
      <p className="auth-links">
        <Link to="/login">Back to sign in</Link>
      </p>
    </div>
  );
}

export function ResetPassword() {
  const [params] = useSearchParams();
  const [password, setPassword] = useState("");
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const submit = (e) => {
    e.preventDefault();
    setError("");
    api
      .post("/auth/password-reset/confirm/", {
        uid: params.get("uid") || "",
        token: params.get("token") || "",
        new_password: password,
      })
      .then((res) => setMessage(res.data.detail))
      .catch((err) => setError(errorText(err)));
  };
  return (
    <div className="auth-card">
      <h1>Choose a new password</h1>
      {message ? (
        <p className="success">
          {message} <Link to="/login">Sign in</Link>
        </p>
      ) : (
        <form onSubmit={submit} className="auth-form">
          <label>
            New password
            <input
              type="password"
              autoComplete="new-password"
              minLength={10}
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
            />
          </label>
          {error && <p className="error pre">{error}</p>}
          <button type="submit">Set password</button>
        </form>
      )}
    </div>
  );
}

export function VerifyEmail() {
  const [params] = useSearchParams();
  const { setUser } = useAuth();
  const [state, setState] = useState({ status: "working", message: "" });
  const sent = useRef(false);

  useEffect(() => {
    if (sent.current) return; // StrictMode runs effects twice in dev; the link only works once
    sent.current = true;
    api
      .post("/auth/verify-email/", { uid: params.get("uid") || "", token: params.get("token") || "" })
      .then((res) => {
        setUser((u) => (u && u.id === res.data.user.id ? res.data.user : u));
        setState({ status: "done", message: "Your email is verified. Your limits have been raised." });
      })
      .catch((err) => setState({ status: "failed", message: errorText(err) }));
  }, [params, setUser]);

  return (
    <div className="auth-card">
      <h1>Email verification</h1>
      {state.status === "working" && <p>Verifying…</p>}
      {state.status === "done" && <p className="success">{state.message}</p>}
      {state.status === "failed" && <p className="error">{state.message}</p>}
      <p className="auth-links">
        <Link to="/">Go to dashboard</Link>
      </p>
    </div>
  );
}
