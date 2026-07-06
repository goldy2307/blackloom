/**
 * Theme handling: persists choice, swaps CSS variables via [data-theme]
 * and swaps the brand logo image (blackloom-light.png / blackloom-dark.png)
 * to match — light-theme pages need the dark-ink logo variant and vice versa.
 */
(function () {
  const STORAGE_KEY = "blackloom-theme";
  const root = document.documentElement;

  function applyTheme(theme) {
    if (theme === "light") {
      root.setAttribute("data-theme", "light");
    } else {
      root.removeAttribute("data-theme"); // dark is the default (no attribute)
    }
    document.querySelectorAll("[data-logo]").forEach((img) => {
      img.src = theme === "light"
        ? "/assets/images/blackloom-dark.png"   // dark logo reads better on light bg
        : "/assets/images/blackloom-light.png"; // light logo reads better on dark bg
    });
    document.querySelectorAll(".theme-toggle").forEach((btn) => {
      btn.textContent = theme === "light" ? "🌙" : "☀️";
      btn.setAttribute("aria-label", theme === "light" ? "Switch to dark theme" : "Switch to light theme");
    });
  }

  function currentTheme() {
    return localStorage.getItem(STORAGE_KEY) || "dark";
  }

  function toggleTheme() {
    const next = currentTheme() === "light" ? "dark" : "light";
    localStorage.setItem(STORAGE_KEY, next);
    applyTheme(next);
  }

  applyTheme(currentTheme());
  document.addEventListener("DOMContentLoaded", () => {
    document.querySelectorAll(".theme-toggle").forEach((btn) => btn.addEventListener("click", toggleTheme));
    applyTheme(currentTheme());
  });
})();