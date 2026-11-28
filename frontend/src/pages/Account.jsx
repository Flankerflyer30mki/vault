import { useState } from "react";
import { useNavigate } from "react-router-dom";
import api, { errorText } from "../api";
import { useAuth } from "../auth";
import { PageHeader } from "../components";
import GoogleButton from "../GoogleButton";

// One small form per action. Each POSTs, shows the server's answer, and updates the signed-in user.
function ActionForm({ title, fields, url, submitLabel, onDone, danger = false, note }) {
  const blank = Object.fromEntries(fields.map((f) => [f.name, ""]));
  const [form, setForm] = useState(blank);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);

  const submit = (e) => {
    e.preventDefault();
    if (danger && !window.confirm(`${title}? This can't be undone.`)) return;
    setBusy(true);
    setError("");
    setMessage("");
    api
      .post(url, form)
      .then((res) => {
        setForm(blank);
        setMessage(onDone?.(res) || "Saved.");
      })
      .catch((err) => setError(errorText(err)))
      .finally(() => setBusy(false));
  };

  return (
    <form onSubmit={submit} className={`auth-form account-section${danger ? " danger-zone" : ""}`}>
      <h3>{title}</h3>
      {note && <p className="hint">{note}</p>}
      {fields.map((f) => (
        <label key={f.name}>
          {f.label}
          <input
            type={f.type || "text"}
            autoComplete={f.autoComplete}
            minLength={f.minLength}
            value={form[f.name]}
            onChange={(e) => setForm({ ...form, [f.name]: e.target.value })}
            required={f.required !== false}
          />
        </label>
      ))}
      {error && <p className="error pre">{error}</p>}
      {message && <p className="success">{message}</p>}
      <button type="submit" className={danger ? "danger" : undefined} disabled={busy}>
        {submitLabel}
      </button>
    </form>
  );
}

function Account() {
  const { user, setUser } = useAuth();
  const navigate = useNavigate();
  const [resent, setResent] = useState("");
  const current = { name: "current_password", label: "Current password", type: "password", autoComplete: "current-password" };
  const newPassword = { name: "new_password", label: "New password", type: "password", autoComplete: "new-password", minLength: 10 };

  const resend = () =>
    api
      .post("/auth/verify-email/resend/")
      .then((res) => setResent(res.data.detail))
      .catch((err) => setResent(errorText(err)));

  return (
    <div className="account-page">
      <PageHeader
        title="Account"
        subtitle={
          <>
            {user.is_guest ? "Guest workspace" : user.email} ·{" "}
            <span className={`tier tier-${user.tier}`}>{user.tier}</span>
          </>
        }
      />
      {user.tier === "unverified" && (
        <p className="hint">
          Your email isn&apos;t verified yet, so your limits are lower.{" "}
          <button type="button" className="link-button" onClick={resend}>
            Resend verification email
          </button>{" "}
          {resent}
        </p>
      )}

      {user.is_guest ? (
        <>
          <div className="auth-form account-section">
            <h3>Save with Google</h3>
            <p className="hint">Keeps all your strategies and runs. Your account is verified straight away.</p>
            <GoogleButton text="continue_with" />
          </div>
          <ActionForm
            title="Save this workspace as an account"
            note={`Keeps all your strategies and runs. Guest workspaces are deleted on ${new Date(
              user.guest_expires_at,
            ).toLocaleDateString()}.`}
            url="/auth/guest/convert/"
            submitLabel="Create account"
            fields={[
              { name: "email", label: "Email", type: "email", autoComplete: "email" },
              { name: "password", label: "Password (at least 10 characters)", type: "password", autoComplete: "new-password", minLength: 10 },
            ]}
            onDone={(res) => {
              setUser(res.data.user);
              return "Account created. Check your email to verify it.";
            }}
          />
        </>
      ) : !user.has_password ? (
        <p className="hint">You sign in with Google, so there&apos;s no password or email to change here.</p>
      ) : (
        <>
          <ActionForm
            title="Change password"
            note="Other devices will be signed out."
            url="/auth/password-change/"
            submitLabel="Change password"
            fields={[current, newPassword]}
            onDone={() => "Password changed."}
          />
          <ActionForm
            title="Change email"
            note="You'll need to verify the new address."
            url="/auth/email-change/"
            submitLabel="Change email"
            fields={[{ name: "new_email", label: "New email", type: "email", autoComplete: "email" }, current]}
            onDone={(res) => {
              setUser(res.data.user);
              return "Email changed. Check your inbox to verify it.";
            }}
          />
        </>
      )}

      <ActionForm
        title="Delete account"
        danger
        note="Permanently deletes your account and all your strategies, backtests, comparisons and optimizations. This can't be undone."
        url="/auth/delete-account/"
        submitLabel="Delete my account"
        fields={user.has_password ? [current] : []}
        onDone={() => {
          setUser(null);
          navigate("/login", { replace: true });
        }}
      />
    </div>
  );
}

export default Account;
