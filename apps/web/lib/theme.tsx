"use client";
import {
  createContext,
  useContext,
  useEffect,
  useState,
  type ReactNode,
} from "react";
import { useSession } from "./session";
const ThemeContext = createContext<{ theme: string; toggle: () => void }>({
  theme: "dark",
  toggle: () => {},
});
export function ThemeProvider({ children }: { children: ReactNode }) {
  const { me } = useSession();
  const key = `chatbot-theme-${me?.id ?? "anonymous"}`;
  const [theme, setTheme] = useState("dark");
  useEffect(() => {
    const media = window.matchMedia("(prefers-color-scheme: dark)");
    const apply = () => {
      let saved: string | null = null;
      try {
        saved = localStorage.getItem(key);
      } catch {
        /* System theme remains available. */
      }
      const next =
        saved === "dark" || saved === "light"
          ? saved
          : media.matches
            ? "dark"
            : "light";
      document.documentElement.dataset.theme = next;
      setTheme(next);
    };
    const timer = window.setTimeout(apply, 0);
    media.addEventListener("change", apply);
    return () => {
      clearTimeout(timer);
      media.removeEventListener("change", apply);
    };
  }, [key]);
  function toggle() {
    const next = theme === "dark" ? "light" : "dark";
    try {
      localStorage.setItem(key, next);
    } catch {
      /* A session-only choice is still useful. */
    }
    setTheme(next);
    document.documentElement.dataset.theme = next;
  }
  return (
    <ThemeContext.Provider value={{ theme, toggle }}>
      {children}
    </ThemeContext.Provider>
  );
}
export function ThemeToggle() {
  const { theme, toggle } = useContext(ThemeContext);
  return (
    <button
      type="button"
      className="quiet-button theme-toggle"
      aria-label={`Switch to ${theme === "dark" ? "light" : "dark"} theme`}
      onClick={toggle}
      data-testid="theme-toggle"
    >
      {theme === "dark" ? "?" : "?"}
      <span>Appearance</span>
    </button>
  );
}
