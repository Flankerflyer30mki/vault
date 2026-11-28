import {
  CornerDownLeft,
  FlaskConical,
  GitCompare,
  LayoutDashboard,
  LogOut,
  Moon,
  Play,
  Plus,
  Search,
  ShieldCheck,
  SlidersHorizontal,
  SunMoon,
  UserRound,
  Workflow,
} from "lucide-react";
import { useEffect, useId, useMemo, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import api, { list } from "./api";
import { useAuth } from "./auth";
import { toggleTheme } from "./theme";

// Ctrl+K / Cmd+K (Raycast/Linear style): jump to a page, backtest a strategy, or run an action, from the keyboard.
// A combobox over a listbox (WAI-ARIA): focus stays in the input, arrows move the highlighted option.

const PAGES = [
  { label: "Dashboard", to: "/", icon: LayoutDashboard, keywords: "home overview" },
  { label: "Strategies", to: "/strategies", icon: Workflow, keywords: "rules templates" },
  { label: "New strategy", to: "/strategies/new", icon: Plus, keywords: "builder create rules" },
  { label: "New backtest", to: "/run", icon: Play, keywords: "run test" },
  { label: "Compare strategies", to: "/compare", icon: GitCompare, keywords: "comparison matrix benchmark" },
  { label: "Optimize a strategy", to: "/optimize", icon: SlidersHorizontal, keywords: "grid search parameters" },
  { label: "AI research", to: "/research", icon: FlaskConical, keywords: "agent llm" },
  { label: "Account", to: "/account", icon: UserRound, keywords: "settings password email profile" },
  { label: "Privacy", to: "/privacy", icon: ShieldCheck, keywords: "data cookies" },
];

// The shortcut as the user's keyboard labels it.
// eslint-disable-next-line react-refresh/only-export-components
export const SHORTCUT = /Mac|iPhone|iPad/.test(globalThis.navigator?.userAgent || "") ? "⌘K" : "Ctrl K";

const OPEN_EVENT = "vault:palette";
// eslint-disable-next-line react-refresh/only-export-components
export const openPalette = () => window.dispatchEvent(new Event(OPEN_EVENT));

// Every word of the query must appear in the label or keywords.
// eslint-disable-next-line react-refresh/only-export-components
export function matches(item, query) {
  const hay = `${item.label} ${item.keywords || ""}`.toLowerCase();
  return query
    .toLowerCase()
    .split(/\s+/)
    .filter(Boolean)
    .every((word) => hay.includes(word));
}

function Palette({ onClose }) {
  const navigate = useNavigate();
  const { logout } = useAuth();
  const [query, setQuery] = useState("");
  const [active, setActive] = useState(0);
  const [strategies, setStrategies] = useState([]);
  const inputRef = useRef(null);
  const listRef = useRef(null);
  const base = useId();

  useEffect(() => {
    inputRef.current?.focus();
    let cancelled = false;
    api
      .get("/strategies/")
      .then((res) => !cancelled && setStrategies(list(res.data)))
      .catch(() => {}); // the palette still works without them
    return () => {
      cancelled = true;
    };
  }, []);

  const groups = useMemo(() => {
    const go = (to) => () => navigate(to);
    const all = [
      { name: "Pages", items: PAGES.map((p) => ({ ...p, run: go(p.to) })) },
      {
        name: "Backtest a strategy",
        items: strategies.map((s) => ({
          label: `Backtest: ${s.name}`,
          keywords: `${s.kind} ${s.is_builtin ? "built-in" : "mine"}`,
          icon: Play,
          run: go(`/run?strategy=${s.id}`),
        })),
      },
      {
        name: "Actions",
        items: [
          { label: "Switch light / dark theme", keywords: "theme dark light mode appearance", icon: SunMoon, run: toggleTheme },
          { label: "Sign out", keywords: "log out logout", icon: LogOut, run: () => logout().then(() => navigate("/login")) },
        ],
      },
    ];
    return all
      .map((g) => ({ ...g, items: query ? g.items.filter((i) => matches(i, query)) : g.items.slice(0, 8) }))
      .filter((g) => g.items.length);
  }, [strategies, query, navigate, logout]);

  const flat = groups.flatMap((g) => g.items);
  const current = Math.min(active, Math.max(flat.length - 1, 0));

  useEffect(() => {
    listRef.current?.querySelector('[aria-selected="true"]')?.scrollIntoView?.({ block: "nearest" });
  }, [current]);

  const choose = (item) => {
    onClose();
    item.run();
  };

  const onKeyDown = (e) => {
    if (e.key === "ArrowDown") setActive((current + 1) % Math.max(flat.length, 1));
    else if (e.key === "ArrowUp") setActive((current - 1 + flat.length) % Math.max(flat.length, 1));
    else if (e.key === "Enter" && flat[current]) choose(flat[current]);
    else if (e.key === "Escape") onClose();
    else return;
    e.preventDefault();
  };

  let index = -1;
  return (
    <div className="palette-overlay" onMouseDown={onClose}>
      <div
        className="palette"
        role="dialog"
        aria-modal="true"
        aria-label="Command palette"
        onMouseDown={(e) => e.stopPropagation()}
      >
        <div className="palette-search">
          <Search size={16} aria-hidden="true" />
          <input
            ref={inputRef}
            role="combobox"
            aria-expanded="true"
            aria-controls={`${base}-list`}
            aria-activedescendant={flat.length ? `${base}-opt-${current}` : undefined}
            aria-label="Search pages, strategies and actions"
            placeholder="Search pages, strategies and actions…"
            value={query}
            onChange={(e) => {
              setQuery(e.target.value);
              setActive(0);
            }}
            onKeyDown={onKeyDown}
          />
          <kbd>Esc</kbd>
        </div>
        <div className="palette-list" id={`${base}-list`} role="listbox" ref={listRef} aria-label="Results">
          {flat.length === 0 && <p className="palette-empty">No results for “{query}”.</p>}
          {groups.map((g) => (
            <div key={g.name} role="group" aria-label={g.name}>
              <div className="palette-group" aria-hidden="true">
                {g.name}
              </div>
              {g.items.map((item) => {
                index += 1;
                const i = index;
                const Icon = item.icon || Moon;
                return (
                  <div
                    key={item.label}
                    id={`${base}-opt-${i}`}
                    role="option"
                    aria-selected={i === current}
                    className="palette-item"
                    onMouseMove={() => i !== current && setActive(i)}
                    onClick={() => choose(item)}
                  >
                    <Icon size={15} aria-hidden="true" />
                    <span>{item.label}</span>
                    {i === current && <CornerDownLeft className="palette-enter" size={13} aria-hidden="true" />}
                  </div>
                );
              })}
            </div>
          ))}
        </div>
        <div className="palette-foot" aria-hidden="true">
          <span>
            <kbd>↑</kbd> <kbd>↓</kbd> move
          </span>
          <span>
            <kbd>↵</kbd> open
          </span>
          <span>
            <kbd>{SHORTCUT}</kbd> toggle
          </span>
        </div>
      </div>
    </div>
  );
}

// Mounted once for signed-in users. Ctrl/Cmd+K toggles; other components open it with the `vault:palette` event.
export default function CommandPalette() {
  const [open, setOpen] = useState(false);
  const returnFocus = useRef(null);

  useEffect(() => {
    const onKey = (e) => {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        setOpen((o) => !o);
      }
    };
    const onOpen = () => setOpen(true);
    window.addEventListener("keydown", onKey);
    window.addEventListener(OPEN_EVENT, onOpen);
    return () => {
      window.removeEventListener("keydown", onKey);
      window.removeEventListener(OPEN_EVENT, onOpen);
    };
  }, []);

  useEffect(() => {
    if (open) {
      returnFocus.current = document.activeElement;
    } else if (returnFocus.current) {
      returnFocus.current.focus?.();
      returnFocus.current = null;
    }
  }, [open]);

  return open ? <Palette onClose={() => setOpen(false)} /> : null;
}
