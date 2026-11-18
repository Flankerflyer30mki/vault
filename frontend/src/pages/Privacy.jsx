import { Link } from "react-router-dom";

// Plain-language privacy notice. Keep it in step with what the code does (docs/reference.md, "Security" and
// "AI assistance"); Google's consent screen links here.
export default function Privacy() {
  return (
    <div className="prose-page">
      <h1>Privacy</h1>
      <p className="hint">Last updated 18 November 2026.</p>

      <p>
        Vault is a personal project: a backtester for trading strategies. This page says what it stores, why, and how
        to delete it.
      </p>

      <h2>What Vault stores</h2>
      <ul>
        <li>
          <strong>Your account:</strong> your email address, an optional display name, and a hashed password if you
          chose one. Your password itself is never stored.
        </li>
        <li>
          <strong>Sign in with Google:</strong> Google tells Vault your name, your email address and that the address
          is verified. Vault gets no access to your Gmail, contacts, Drive or anything else in your Google account.
        </li>
        <li>
          <strong>Your work:</strong> the strategies you save and the backtests, comparisons, optimizations and research
          runs you start, with their results.
        </li>
        <li>
          <strong>AI requests:</strong> if you describe a strategy in words or start a research run, the text you type
          is stored for up to 30 days and sent to Groq, the AI provider, to generate the answer. Your email and account
          details are not sent.
        </li>
      </ul>

      <h2>Cookies</h2>
      <p>
        Two cookies, both needed for the site to work: one keeps you signed in, the other protects forms against
        cross-site request forgery. There are no advertising, analytics or tracking cookies.
      </p>

      <h2>Who else handles data</h2>
      <ul>
        <li>Vercel (serves the website) and Render (runs the server and database) process requests to operate the site.</li>
        <li>Google, only if you use Sign in with Google.</li>
        <li>Groq, only for AI requests, as described above.</li>
      </ul>
      <p>Vault does not sell or share your data with anyone else, and shows no ads.</p>

      <h2>Deleting your data</h2>
      <p>
        You can delete your account at any time on the <Link to="/account">Account</Link> page. This permanently removes
        your account and everything you created. Guest workspaces are deleted automatically after 7 days unless saved
        as an account.
      </p>

      <h2>Contact</h2>
      <p>
        Questions or requests: open an issue on the project&apos;s{" "}
        <a href="https://github.com/Flankerflyer30mki/vault/issues" target="_blank" rel="noreferrer">
          GitHub page
        </a>
        .
      </p>
    </div>
  );
}
