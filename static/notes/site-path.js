(function () {
  function getSiteBase() {
    return String(window.SITE_BASE || "").replace(/\/$/, "");
  }

  function siteUrl(path) {
    if (path && (path.startsWith("http://") || path.startsWith("https://"))) {
      return path;
    }
    const base = getSiteBase();
    if (!path || path === "/") {
      return (base || "") + "/";
    }
    if (!path.startsWith("/")) {
      path = "/" + path;
    }
    return base + path;
  }

  window.siteUrl = siteUrl;
})();
