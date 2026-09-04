(function () {
  var key = "artek-theme";
  var eventName = "artek-theme-change";
  var darkQuery = window.matchMedia("(prefers-color-scheme: dark)");
  var root = document.documentElement;
  var themeColor = document.querySelector('meta[name="theme-color"]');

  function preference() {
    try {
      var stored = window.localStorage.getItem(key);
      return stored === "light" || stored === "dark" || stored === "system" ? stored : "system";
    } catch (_error) {
      return "system";
    }
  }

  function apply() {
    var selected = preference();
    var resolved = selected === "system" ? (darkQuery.matches ? "dark" : "light") : selected;
    root.dataset.theme = selected;
    if (themeColor) {
      themeColor.setAttribute("content", resolved === "dark" ? "#0d1727" : "#f4f7fb");
    }
  }

  apply();
  darkQuery.addEventListener("change", apply);
  window.addEventListener(eventName, apply);
  window.addEventListener("storage", function (event) {
    if (event.key === key) apply();
  });
})();
