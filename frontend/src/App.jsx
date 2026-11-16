import { BrowserRouter, Link, NavLink, Route, Routes, useNavigate } from "react-router-dom";
import { AuthProvider, GuestOnly, RequireAuth, useAuth } from "./auth";
import Account from "./pages/Account";
import { ForgotPassword, Login, ResetPassword, Signup, VerifyEmail } from "./pages/Auth";
import Comparison from "./pages/Comparison";
import Dashboard from "./pages/Dashboard";
import OptimizationTrigger from "./pages/OptimizationTrigger";
import RunDetail from "./pages/RunDetail";
import RunTrigger from "./pages/RunTrigger";
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
          <NavLink to="/optimize">Optimize</NavLink>
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
            <Route path="/" element={page(<Dashboard />)} />
            <Route path="/account" element={page(<Account />)} />
            <Route path="/strategies" element={page(<StrategyList />)} />
            <Route path="/run" element={page(<RunTrigger />)} />
            <Route path="/runs/:id" element={page(<RunDetail />)} />
            <Route path="/optimize" element={page(<OptimizationTrigger />)} />
            <Route path="/optimize/:id" element={page(<Comparison />)} />
          </Routes>
        </div>
      </AuthProvider>
    </BrowserRouter>
  );
}

export default App;
