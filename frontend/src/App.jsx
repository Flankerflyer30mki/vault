import {
  FlaskConical,
  GitCompare,
  LayoutDashboard,
  LogOut,
  Moon,
  Play,
  SlidersHorizontal,
  Sun,
  UserRound,
  Workflow,
} from "lucide-react";
import { BrowserRouter, Link, NavLink, Route, Routes, useLocation, useNavigate } from "react-router-dom";
import { AuthProvider, GuestOnly, RequireAuth, useAuth } from "./auth";
import { useTheme } from "./theme";
import Account from "./pages/Account";
import { ForgotPassword, Login, ResetPassword, Signup, VerifyEmail } from "./pages/Auth";
import ComparisonTrigger from "./pages/ComparisonTrigger";
import Dashboard from "./pages/Dashboard";
import ExperimentDetail from "./pages/ExperimentDetail";
import OptimizationTrigger from "./pages/OptimizationTrigger";
import Privacy from "./pages/Privacy";
import Research from "./pages/Research";
import ResearchDetail from "./pages/ResearchDetail";
import RunDetail from "./pages/RunDetail";
import RunTrigger from "./pages/RunTrigger";
import StrategyBuilder from "./pages/StrategyBuilder";
import StrategyList from "./pages/StrategyList";
import "./App.css";

const NAV = [
  {
    label: "Workspace",
    items: [
      { to: "/", label: "Dashboard", icon: LayoutDashboard, end: true },
      { to: "/strategies", label: "Strategies", icon: Workflow },
      { to: "/run", label: "New backtest", icon: Play },
    ],
  },
  {
    label: "Experiments",
    items: [
      { to: "/compare", label: "Compare", icon: GitCompare },
      { to: "/optimize", label: "Optimize", icon: SlidersHorizontal },
      { to: "/research", label: "AI research", icon: FlaskConical },
    ],
  },
];

function Brand() {
  return (
    <Link to="/" className="brand">
      <span className="brand-mark" aria-hidden="true">
        V
      </span>
      Vault
    </Link>
  );
}

function ThemeToggle({ asNavItem = false }) {
  const [theme, toggle] = useTheme();
  const Icon = theme === "dark" ? Sun : Moon;
  const label = theme === "dark" ? "Light theme" : "Dark theme";
  if (asNavItem) {
    return (
      <button type="button" className="nav-item" onClick={toggle} title={label}>
        <Icon size={15} aria-hidden="true" />
        <span className="foot-text">{label}</span>
      </button>
    );
  }
  return (
    <button type="button" className="theme-toggle" onClick={toggle} aria-label={label} title={label}>
      <Icon size={16} aria-hidden="true" />
    </button>
  );
}

function Sidebar() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  return (
    <aside className="sidebar">
      <Brand />
      <nav aria-label="Main" className="nav-groups">
        {NAV.map((group) => (
          <div key={group.label} className="nav-group">
            <div className="nav-label">{group.label}</div>
            {group.items.map(({ to, label, icon: Icon, end }) => (
              <NavLink key={to} to={to} end={end} className="nav-item">
                <Icon size={15} aria-hidden="true" />
                {label}
              </NavLink>
            ))}
          </div>
        ))}
      </nav>
      <div className="sidebar-foot">
        <NavLink to="/account" className="nav-item nav-user" title="Account">
          <UserRound size={15} aria-hidden="true" />
          <span className="foot-text">{user.is_guest ? "Guest" : user.display_name || user.email}</span>
        </NavLink>
        <ThemeToggle asNavItem />
        <button
          type="button"
          className="nav-item"
          title="Sign out"
          onClick={() => logout().then(() => navigate("/login"))}
        >
          <LogOut size={15} aria-hidden="true" />
          <span className="foot-text">Sign out</span>
        </button>
        <div className="sidebar-links">
          <Link to="/privacy">Privacy</Link>
          <a href="https://github.com/Flankerflyer30mki/vault" target="_blank" rel="noreferrer">
            Source
          </a>
        </div>
      </div>
    </aside>
  );
}

function Topbar() {
  return (
    <header className="topbar">
      <Brand />
      <ThemeToggle />
    </header>
  );
}

function Footer() {
  return (
    <footer className="site-footer">
      <Link to="/privacy">Privacy</Link> ·{" "}
      <a href="https://github.com/Flankerflyer30mki/vault" target="_blank" rel="noreferrer">
        Source
      </a>
    </footer>
  );
}

function Banner() {
  const { user } = useAuth();
  if (!user) return null;
  if (user.is_guest) {
    return (
      <div className="banner">
        You&apos;re using a guest workspace. It will be deleted on{" "}
        {new Date(user.guest_expires_at).toLocaleDateString()}.{" "}
        <Link to="/account">Save it as an account</Link>
      </div>
    );
  }
  if (user.tier === "unverified") {
    return (
      <div className="banner">
        Check your inbox to verify <strong>{user.email}</strong> and raise your limits.{" "}
        <Link to="/account">Resend email</Link>
      </div>
    );
  }
  return null;
}

const page = (el) => <RequireAuth>{el}</RequireAuth>;
const open = (el) => <GuestOnly>{el}</GuestOnly>;

// Signed in: sidebar + page. Signed out (or still loading): a slim top bar over centred content.
function Shell({ children }) {
  const { user } = useAuth();
  const { pathname } = useLocation();
  const content = (
    <main className="content" key={pathname}>
      {children}
    </main>
  );
  if (user === undefined) {
    // Asking /api/auth/me/; on a cold server this can take a while, so say so quietly instead of flashing a layout.
    return (
      <div className="boot">
        <span className="brand-mark" aria-hidden="true">
          V
        </span>
        <p className="hint">Loading…</p>
      </div>
    );
  }
  if (!user) {
    return (
      <div className="main">
        <Topbar />
        {content}
        <Footer />
      </div>
    );
  }
  return (
    <div className="shell">
      <Sidebar />
      <div className="main">
        <Banner />
        {content}
      </div>
    </div>
  );
}

function App() {
  return (
    <BrowserRouter>
      <AuthProvider>
        <Shell>
          <Routes>
            <Route path="/login" element={open(<Login />)} />
            <Route path="/signup" element={open(<Signup />)} />
            <Route path="/forgot-password" element={<ForgotPassword />} />
            <Route path="/reset-password" element={<ResetPassword />} />
            <Route path="/verify-email" element={<VerifyEmail />} />
            <Route path="/privacy" element={<Privacy />} />
            <Route path="/" element={page(<Dashboard />)} />
            <Route path="/account" element={page(<Account />)} />
            <Route path="/strategies" element={page(<StrategyList />)} />
            <Route path="/strategies/new" element={page(<StrategyBuilder />)} />
            <Route path="/strategies/:id/edit" element={page(<StrategyBuilder />)} />
            <Route path="/run" element={page(<RunTrigger />)} />
            <Route path="/runs/:id" element={page(<RunDetail />)} />
            <Route path="/optimize" element={page(<OptimizationTrigger />)} />
            <Route path="/compare" element={page(<ComparisonTrigger />)} />
            <Route path="/experiments/:id" element={page(<ExperimentDetail />)} />
            <Route path="/optimize/:id" element={page(<ExperimentDetail />)} />
            <Route path="/research" element={page(<Research />)} />
            <Route path="/research/:id" element={page(<ResearchDetail />)} />
          </Routes>
        </Shell>
      </AuthProvider>
    </BrowserRouter>
  );
}

export default App;
