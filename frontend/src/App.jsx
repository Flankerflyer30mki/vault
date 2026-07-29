import { BrowserRouter, Routes, Route, Link } from "react-router-dom";
import StrategyList from "./pages/StrategyList";
import RunTrigger from "./pages/RunTrigger";
import RunDetail from "./pages/RunDetail";
import OptimizationTrigger from "./pages/OptimizationTrigger";
import Comparison from "./pages/Comparison";
import "./App.css";

function App() {
  return (
    <BrowserRouter>
      <nav className="navbar">
        <h2>Vault</h2>
        <Link to="/">Strategies</Link>
        <Link to="/run">New Backtest</Link>
        <Link to="/optimize">Optimize</Link>
      </nav>
      <div className="content">
        <Routes>
          <Route path="/" element={<StrategyList />} />
          <Route path="/run" element={<RunTrigger />} />
          <Route path="/runs/:id" element={<RunDetail />} />
          <Route path="/optimize" element={<OptimizationTrigger />} />
          <Route path="/optimize/:id" element={<Comparison />} />
        </Routes>
      </div>
    </BrowserRouter>
  );
}

export default App;
