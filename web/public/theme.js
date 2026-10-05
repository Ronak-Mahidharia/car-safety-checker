// Runs before the page is drawn, so a saved light or dark choice shows without a flash of the other
// theme. With no saved choice, the page follows the device's setting. The key and the colors match
// src/lib/theme.ts, and a test checks that.
(function () {
  try {
    var theme = window.localStorage.getItem("car-safety-checker-theme");
    if (theme !== "light" && theme !== "dark") return;
    document.documentElement.dataset.theme = theme;
    var color = theme === "dark" ? "#0b1020" : "#f4f6fa";
    var metas = document.querySelectorAll('meta[name="theme-color"]');
    for (var i = 0; i < metas.length; i++) metas[i].setAttribute("content", color);
  } catch (error) {
    // storage blocked: follow the device's setting
  }
})();
