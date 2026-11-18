import { BrowserRouter, Link, NavLink, Route, Routes, useNavigate } from "react-router-dom";
import { AuthProvider, GuestOnly, RequireAuth, useAuth } from "./auth";
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

function Nav() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  return (
    <nav className="navbar">
      <h2>
        <Link to="/">Vault</Link>
      </h2>
      {user && (
        <>
          <NavLink to="/" end>
            Dashboard
          </NavLink>
          <NavLink to="/strategies">Strategies</NavLink>
          <NavLink to="/run">New Backtest</NavLink>
          <NavLink to="/compare">Compare</NavLink>
          <NavLink to="/optimize">Optimize</NavLink>
          <NavLink to="/research">Research</NavLink>
          <span className="nav-spacer" />
          <NavLink to="/account" className="nav-user">
            {user.is_guest ? "Guest" : user.display_name || user.email}
          </NavLink>
          <button type="button" className="link-button nav-logout" onClick={() => logout().then(() => navigate("/login"))}>
            Sign out
          </button>
        </>
      )}
    </nav>
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

function App() {
  return (
    <BrowserRouter>
      <AuthProvider>
        <Nav />
        <Banner />
        <div className="content">
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
        </div>
        <footer className="site-footer">
          <Link to="/privacy">Privacy</Link> ·{" "}
          <a href="https://github.com/Flankerflyer30mki/vault" target="_blank" rel="noreferrer">
            Source
          </a>
        </footer>
      </AuthProvider>
    </BrowserRouter>
  );
}

export default App;
