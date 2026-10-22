// Interface language of the site (EN | FR switch). Shared by every show's catalog and pages.
// The page is written in its show's language; once a visitor picks a language, it is remembered
// in the browser and applied to every page. Only the interface changes: episodes stay as written.
// Texts come from docs/i18n.json, built from engine/locales/*.yaml by engine/site.py.
(() => {
  const KEY = "ui-lang";
  const root = new URL(".", document.currentScript.src).href;  // docs/, wherever the page is
  const pageLang = document.documentElement.lang || "en";
  let dict = null;
  let lang = pageLang;
  try { lang = localStorage.getItem(KEY) || pageLang; } catch {}
  const listeners = [];

  const pick = (key) => (dict && ((dict[lang] || {})[key] ?? (dict[pageLang] || {})[key] ?? (dict.en || {})[key]));
  const t = (key, vars = {}) => {
    let value = pick(key);
    if (value == null) return key;
    if (typeof value === "object") value = vars.n === 1 ? value.one : value.other;
    return String(value).replace(/\{(\w+)\}/g, (_, name) => (vars[name] ?? ""));
  };
  const locale = () => (dict && dict[lang] && dict[lang].locale) || "en-GB";
  const date = (iso, style) => {
    const options = style === "day" ? { weekday: "short", day: "numeric", month: "short", year: "numeric" }
      : style === "month" ? { month: "long", year: "numeric" }
      : { weekday: "long", day: "numeric", month: "long", year: "numeric" };
    return new Date(iso + "T12:00:00").toLocaleDateString(locale(), options);
  };

  const apply = (scope = document) => {
    if (!dict) return;
    document.documentElement.dataset.uiLang = lang;
    scope.querySelectorAll("[data-i18n]").forEach((el) => {
      el.textContent = t(el.dataset.i18n, JSON.parse(el.dataset.i18nVars || "{}"));
    });
    for (const attr of ["title", "placeholder", "aria-label"]) {
      scope.querySelectorAll(`[data-i18n-${attr}]`).forEach((el) => el.setAttribute(attr, t(el.getAttribute(`data-i18n-${attr}`))));
    }
    scope.querySelectorAll("[data-date]").forEach((el) => { el.textContent = date(el.dataset.date, el.dataset.dateStyle); });
    document.querySelectorAll("[data-lang]").forEach((b) => b.setAttribute("aria-pressed", String(b.dataset.lang === lang)));
  };

  const setLang = (next) => {
    lang = next;
    try { localStorage.setItem(KEY, next); } catch {}
    apply();
    listeners.forEach((fn) => fn(lang));
  };

  document.addEventListener("click", (e) => {
    const button = e.target.closest("[data-lang]");
    if (button) setLang(button.dataset.lang);
  });

  const ready = fetch(root + "i18n.json", { cache: "no-cache" })
    .then((r) => (r.ok ? r.json() : null))
    .catch(() => null)
    .then((data) => {
      dict = data;
      if (dict && !dict[lang]) lang = pageLang;
      if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", () => apply());
      else apply();
      return dict;
    });

  window.I18N = { t, date, apply, ready, onChange: (fn) => listeners.push(fn), get lang() { return lang; } };
})();
