(function () {
  const CONFIG_KEY = "note-site-github";

  function getDefaults() {
    const fromPage = window.NOTES_REPO_CONFIG || {};
    return {
      owner: fromPage.owner || "Yujiushi",
      repo: fromPage.repo || "my-note-website",
      branch: fromPage.branch || "main",
      token: "",
    };
  }

  function loadConfig() {
    try {
      const saved = JSON.parse(localStorage.getItem(CONFIG_KEY) || "{}");
      return Object.assign({}, getDefaults(), saved);
    } catch {
      return Object.assign({}, getDefaults());
    }
  }

  function saveConfig(config) {
    localStorage.setItem(
      CONFIG_KEY,
      JSON.stringify({
        owner: config.owner,
        repo: config.repo,
        branch: config.branch,
        token: config.token,
      })
    );
  }

  function utf8ToBase64(text) {
    const bytes = new TextEncoder().encode(text);
    let binary = "";
    bytes.forEach(function (b) {
      binary += String.fromCharCode(b);
    });
    return btoa(binary);
  }

  function base64ToUtf8(base64) {
    const binary = atob(base64.replace(/\n/g, ""));
    const bytes = Uint8Array.from(binary, function (c) {
      return c.charCodeAt(0);
    });
    return new TextDecoder().decode(bytes);
  }

  function apiUrl(config, path) {
    const q =
      config.branch && config.branch !== "main"
        ? "?ref=" + encodeURIComponent(config.branch)
        : "";
    return (
      "https://api.github.com/repos/" +
      encodeURIComponent(config.owner) +
      "/" +
      encodeURIComponent(config.repo) +
      "/contents/" +
      path
        .split("/")
        .map(encodeURIComponent)
        .join("/") +
      q
    );
  }

  function headers(config) {
    return {
      Authorization: "Bearer " + config.token,
      Accept: "application/vnd.github+json",
      "X-GitHub-Api-Version": "2022-11-28",
    };
  }

  async function getFile(config, path) {
    const res = await fetch(apiUrl(config, path), { headers: headers(config) });
    if (res.status === 404) return null;
    if (!res.ok) {
      const err = await res.json().catch(function () {
        return {};
      });
      throw new Error(err.message || "读取文件失败：" + path);
    }
    const data = await res.json();
    if (Array.isArray(data)) throw new Error("路径指向目录而非文件：" + path);
    return {
      content: base64ToUtf8(data.content),
      sha: data.sha,
    };
  }

  function arrayBufferToBase64(buffer) {
    const bytes = new Uint8Array(buffer);
    let binary = "";
    const chunk = 0x8000;
    for (let i = 0; i < bytes.length; i += chunk) {
      binary += String.fromCharCode.apply(null, bytes.subarray(i, i + chunk));
    }
    return btoa(binary);
  }

  async function fileExists(config, path) {
    const res = await fetch(apiUrl(config, path), { headers: headers(config) });
    if (res.status === 404) return null;
    if (!res.ok) {
      const err = await res.json().catch(function () {
        return {};
      });
      throw new Error(err.message || "检查文件失败：" + path);
    }
    const data = await res.json();
    if (Array.isArray(data)) throw new Error("路径指向目录而非文件：" + path);
    return { sha: data.sha };
  }

  async function putBinaryFile(config, path, arrayBuffer, message, sha) {
    const body = {
      message: message,
      content: arrayBufferToBase64(arrayBuffer),
      branch: config.branch || "main",
    };
    if (sha) body.sha = sha;

    const res = await fetch(apiUrl(config, path).replace(/\?.*$/, ""), {
      method: "PUT",
      headers: Object.assign({ "Content-Type": "application/json" }, headers(config)),
      body: JSON.stringify(body),
    });

    if (!res.ok) {
      const err = await res.json().catch(function () {
        return {};
      });
      throw new Error(err.message || "写入文件失败：" + path);
    }
    return res.json();
  }

  async function putFile(config, path, content, message, sha) {
    const body = {
      message: message,
      content: utf8ToBase64(content),
      branch: config.branch || "main",
    };
    if (sha) body.sha = sha;

    const res = await fetch(apiUrl(config, path).replace(/\?.*$/, ""), {
      method: "PUT",
      headers: Object.assign({ "Content-Type": "application/json" }, headers(config)),
      body: JSON.stringify(body),
    });

    if (!res.ok) {
      const err = await res.json().catch(function () {
        return {};
      });
      throw new Error(err.message || "写入文件失败：" + path);
    }
    return res.json();
  }

  async function deleteFile(config, path, message, sha) {
    const res = await fetch(apiUrl(config, path).replace(/\?.*$/, ""), {
      method: "DELETE",
      headers: Object.assign({ "Content-Type": "application/json" }, headers(config)),
      body: JSON.stringify({
        message: message,
        sha: sha,
        branch: config.branch || "main",
      }),
    });

    if (!res.ok) {
      const err = await res.json().catch(function () {
        return {};
      });
      throw new Error(err.message || "删除文件失败：" + path);
    }
    return res.json();
  }

  async function testConnection(config) {
    const res = await fetch(
      "https://api.github.com/repos/" +
        encodeURIComponent(config.owner) +
        "/" +
        encodeURIComponent(config.repo),
      { headers: headers(config) }
    );
    if (!res.ok) {
      const err = await res.json().catch(function () {
        return {};
      });
      throw new Error(err.message || "无法连接仓库，请检查配置与 Token");
    }
    return res.json();
  }

  function requireToken(onMissing) {
    const config = loadConfig();
    if (!config.token) {
      if (typeof onMissing === "function") onMissing();
      throw new Error("未配置 Token");
    }
    return config;
  }

  function getAuthHeaders(config) {
    config = config || loadConfig();
    return { Authorization: "Bearer " + config.token };
  }

  window.GitHubClient = {
    loadConfig: loadConfig,
    saveConfig: saveConfig,
    getFile: getFile,
    fileExists: fileExists,
    putFile: putFile,
    putBinaryFile: putBinaryFile,
    deleteFile: deleteFile,
    testConnection: testConnection,
    requireToken: requireToken,
    getAuthHeaders: getAuthHeaders,
  };
})();
