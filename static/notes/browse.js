(function () {
  let manifest = null;
  let categoryId = "";
  let folderPath = "";

  function getParams() {
    const params = new URLSearchParams(window.location.search);
    return {
      categoryId: params.get("c") || "",
      folderPath: params.get("p") || "",
    };
  }

  function escapeHtml(text) {
    return String(text)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function setStatus(type, message) {
    const el = document.getElementById("browse-status");
    if (!el) return;
    el.className = "upload-status upload-status--" + type;
    el.textContent = message;
    el.hidden = !message;
  }

  function getConfig() {
    return GitHubClient.loadConfig();
  }

  function requireToken() {
    const config = getConfig();
    if (!config.token) {
      setStatus("error", "请先在 ⚙️ 中配置 GitHub Token");
      document.getElementById("dialog-github").showModal();
      throw new Error("未配置 Token");
    }
    return config;
  }

  async function fetchRemoteManifest(config) {
    const file = await GitHubClient.getFile(config, "notes.json");
    if (file) {
      return { manifest: JSON.parse(file.content), sha: file.sha };
    }

    if (!manifest) {
      throw new Error(
        "远程仓库还没有 notes.json，且本地目录未加载。请先把项目 push 到 GitHub，或刷新页面后重试。"
      );
    }

    setStatus(
      "info",
      "远程仓库尚无 notes.json，将用当前本地目录自动初始化…"
    );
    return {
      manifest: JSON.parse(JSON.stringify(manifest)),
      sha: null,
    };
  }

  async function saveManifest(config, data, sha, message) {
    await GitHubClient.putFile(
      config,
      "notes.json",
      NoteManifest.serialize(data),
      message,
      sha || undefined
    );
    manifest = data;
  }

  function renderBreadcrumb() {
    const el = document.getElementById("breadcrumb");
    const crumbs = NoteManifest.getBreadcrumb(manifest, categoryId, folderPath);
    el.innerHTML = crumbs
      .map(function (crumb, i) {
        if (i === crumbs.length - 1) {
          return "<span>" + escapeHtml(crumb.label) + "</span>";
        }
        return (
          '<a href="' + escapeHtml(crumb.href) + '">' + escapeHtml(crumb.label) + "</a>"
        );
      })
      .join('<span class="breadcrumb-sep">/</span>');
  }

  function renderHeader() {
    const category = NoteManifest.getCategory(manifest, categoryId);
    const titleEl = document.getElementById("browse-title");
    const descEl = document.getElementById("browse-desc");

    if (!category) {
      titleEl.textContent = "未找到分类";
      descEl.textContent = "";
      document.title = "未找到 · 我的笔记";
      return;
    }

    if (!folderPath) {
      titleEl.textContent = category.emoji + " " + category.label;
      descEl.textContent = category.desc || "";
      document.title = category.label + " · 我的笔记";
      return;
    }

    const parts = NoteManifest.splitPath(folderPath);
    let container = category.children || [];
    let folder = null;

    parts.forEach(function (slug) {
      folder = container.find(function (item) {
        return item.type === "folder" && item.slug === slug;
      });
      if (folder) container = folder.children || [];
    });

    titleEl.textContent = folder ? "📁 " + folder.name : "文件夹";
    descEl.textContent = folder
      ? countDesc(folder.children)
      : "";
    document.title = (folder ? folder.name : "文件夹") + " · 我的笔记";
  }

  function fileIcon(filename) {
    const ext = String(filename).split(".").pop().toLowerCase();
    if (["jpg", "jpeg", "png", "gif", "webp", "svg", "bmp"].indexOf(ext) >= 0) return "🖼️";
    if (ext === "pdf") return "📕";
    if (["doc", "docx"].indexOf(ext) >= 0) return "📘";
    if (["xls", "xlsx", "csv"].indexOf(ext) >= 0) return "📗";
    if (["ppt", "pptx"].indexOf(ext) >= 0) return "📙";
    if (["zip", "rar", "7z"].indexOf(ext) >= 0) return "🗜️";
    return "📎";
  }

  function countDesc(children) {
    const n = NoteManifest.countItems(children || []);
    return n ? "共 " + n + " 项" : "空文件夹";
  }

  function renderFileList() {
    const list = document.getElementById("file-list");
    const children = NoteManifest.getContainer(manifest, categoryId, folderPath);

    if (!children) {
      list.innerHTML = '<li class="file-list-empty">目录不存在</li>';
      return;
    }

    if (!children.length) {
      list.innerHTML =
        '<li class="file-list-empty">文件夹为空，可新建文件夹、页面或上传文件</li>';
      return;
    }

    const sorted = children.slice().sort(function (a, b) {
      if (a.type !== b.type) return a.type === "folder" ? -1 : 1;
      const nameA = a.type === "folder" ? a.name : a.title;
      const nameB = b.type === "folder" ? b.name : b.title;
      return nameA.localeCompare(nameB, "zh-CN");
    });

    list.innerHTML = sorted
      .map(function (item) {
        if (item.type === "folder") {
          const childPath = folderPath
            ? folderPath + "/" + item.slug
            : item.slug;
          const count = NoteManifest.countItems(item.children);
          return (
            '<li class="file-item file-item--folder">' +
            '<a href="' +
            NoteManifest.browseHref(categoryId, childPath) +
            '">' +
            '<span class="file-icon">📁</span>' +
            '<span class="file-name">' +
            escapeHtml(item.name) +
            "</span>" +
            '<span class="file-meta">' +
            count +
            " 项</span>" +
            "</a></li>"
          );
        }

        if (item.type === "file") {
          return (
            '<li class="file-item file-item--file">' +
            '<a href="' +
            NoteManifest.fileHref(categoryId, folderPath, item.filename) +
            '" target="_blank" rel="noopener noreferrer">' +
            '<span class="file-icon">' +
            fileIcon(item.filename) +
            "</span>" +
            '<span class="file-name">' +
            escapeHtml(item.title || item.filename) +
            "</span>" +
            '<span class="file-meta">' +
            escapeHtml(item.date || "") +
            "</span>" +
            "</a></li>"
          );
        }

        return (
          '<li class="file-item file-item--page">' +
          '<a href="' +
          NoteManifest.pageHref(categoryId, folderPath, item.slug) +
          '">' +
          '<span class="file-icon">📄</span>' +
          '<span class="file-name">' +
          escapeHtml(item.title) +
          "</span>" +
          '<span class="file-meta">' +
          escapeHtml(item.date || "") +
          "</span>" +
          "</a></li>"
        );
      })
      .join("");
  }

  async function createPage(title, content, tag) {
    const config = requireToken();
    const slug = NoteManifest.slugify(title);
    const date = NoteManifest.today();
    const repoPath = NoteManifest.pageRepoPath(categoryId, folderPath, slug);

    const remote = await fetchRemoteManifest(config);
    const data = remote.manifest;
    const category = NoteManifest.getCategory(data, categoryId);
    if (!category) throw new Error("分类不存在");

    const existing = await GitHubClient.getFile(config, repoPath);
    if (existing) throw new Error("同名页面已存在，请换标题");

    const bodyHtml = window.markdownToHtml(content);
    const noteHtml = buildNoteHtml({
      manifest: data,
      categoryId: categoryId,
      categoryLabel: category.label,
      folderPath: folderPath,
      title: title,
      date: date,
      tag: tag || "",
      bodyHtml: bodyHtml,
    });

    setStatus("info", "正在创建页面…");
    NoteManifest.addPage(data, categoryId, folderPath, {
      title: title,
      slug: slug,
      date: date,
      search: title,
    });

    await GitHubClient.putFile(config, repoPath, noteHtml, "新建页面：" + title);
    await saveManifest(config, data, remote.sha, "更新目录：" + title);

    setStatus("success", "页面已创建！约 1～3 分钟后可见。");
    manifest = data;
    renderAll();
  }

  async function createFolder(name) {
    const config = requireToken();
    const remote = await fetchRemoteManifest(config);
    const data = remote.manifest;

    setStatus("info", "正在创建文件夹…");
    NoteManifest.addFolder(data, categoryId, folderPath, name);
    await saveManifest(config, data, remote.sha, "新建文件夹：" + name);

    setStatus("success", "文件夹「" + name + "」已创建");
    manifest = data;
    renderAll();
  }

  const UPLOAD_TEXT_EXTS = ["md", "markdown", "txt", "html"];
  const UPLOAD_BINARY_EXTS = [
    "pdf", "doc", "docx", "xls", "xlsx", "csv", "ppt", "pptx",
    "jpg", "jpeg", "png", "gif", "webp", "svg", "bmp",
    "zip", "rar", "7z",
  ];
  const MAX_UPLOAD_BYTES = 20 * 1024 * 1024;

  function sanitizeFilename(name) {
    return String(name).replace(/[\\/:*?"<>|]/g, "_").trim() || "file";
  }

  function readFileAsArrayBuffer(file) {
    return new Promise(function (resolve, reject) {
      const reader = new FileReader();
      reader.onload = function () {
        resolve(reader.result);
      };
      reader.onerror = function () {
        reject(new Error("读取文件失败"));
      };
      reader.readAsArrayBuffer(file);
    });
  }

  async function uploadBinaryFile(file) {
    const config = requireToken();
    const safeName = sanitizeFilename(file.name);
    const ext = safeName.split(".").pop().toLowerCase();
    const baseName = safeName.replace(/\.[^.]+$/, "");
    const repoPath = NoteManifest.fileRepoPath(categoryId, folderPath, safeName);

    if (await GitHubClient.fileExists(config, repoPath)) {
      throw new Error("同名文件已存在");
    }

    const remote = await fetchRemoteManifest(config);
    const data = remote.manifest;
    const category = NoteManifest.getCategory(data, categoryId);
    if (!category) throw new Error("分类不存在");

    setStatus("info", "正在上传 " + safeName + "…");
    const buffer = await readFileAsArrayBuffer(file);
    await GitHubClient.putBinaryFile(
      config,
      repoPath,
      buffer,
      "上传附件：" + safeName
    );

    NoteManifest.addFile(data, categoryId, folderPath, {
      title: baseName,
      filename: safeName,
      date: NoteManifest.today(),
      search: baseName + " " + ext,
    });
    await saveManifest(config, data, remote.sha, "更新目录：" + safeName);

    setStatus("success", "文件已上传！约 1～3 分钟后可在线访问。");
    manifest = data;
    renderAll();
  }

  async function uploadFile(file) {
    if (file.size > MAX_UPLOAD_BYTES) {
      throw new Error("文件不能超过 20MB");
    }

    const name = file.name;
    const ext = name.split(".").pop().toLowerCase();
    const baseName = name.replace(/\.[^.]+$/, "");

    if (UPLOAD_BINARY_EXTS.indexOf(ext) >= 0) {
      await uploadBinaryFile(file);
      return;
    }

    if (ext === "html") {
      const config = requireToken();
      const slug = NoteManifest.slugify(baseName);
      const repoPath = NoteManifest.pageRepoPath(categoryId, folderPath, slug);
      const text = await readFileAsText(file);

      const remote = await fetchRemoteManifest(config);
      const data = remote.manifest;
      const category = NoteManifest.getCategory(data, categoryId);

      const existing = await GitHubClient.getFile(config, repoPath);
      if (existing) throw new Error("同名文件已存在");

      setStatus("info", "正在上传 HTML…");
      NoteManifest.addPage(data, categoryId, folderPath, {
        title: baseName,
        slug: slug,
        date: NoteManifest.today(),
        search: baseName,
      });

      await GitHubClient.putFile(config, repoPath, text, "上传文件：" + name);
      await saveManifest(config, data, remote.sha, "更新目录：" + name);

      setStatus("success", "文件已上传");
      manifest = data;
      renderAll();
      return;
    }

    if (ext === "md" || ext === "markdown" || ext === "txt") {
      const text = await readFileAsText(file);
      await createPage(baseName, text);
      return;
    }

    throw new Error(
      "不支持的文件类型。支持：笔记 .md/.txt/.html，以及图片、PDF、Word、Excel 等附件"
    );
  }

  function readFileAsText(file) {
    return new Promise(function (resolve, reject) {
      const reader = new FileReader();
      reader.onload = function () {
        resolve(reader.result);
      };
      reader.onerror = reject;
      reader.readAsText(file, "UTF-8");
    });
  }

  function renderAll() {
    renderBreadcrumb();
    renderHeader();
    renderFileList();
  }

  function setupDialogs() {
    document.querySelectorAll("[data-close]").forEach(function (btn) {
      btn.addEventListener("click", function () {
        btn.closest("dialog").close();
      });
    });

    document.getElementById("btn-new-folder").addEventListener("click", function () {
      document.getElementById("form-folder").reset();
      document.getElementById("dialog-folder").showModal();
    });

    document.getElementById("form-folder").addEventListener("submit", async function (e) {
      e.preventDefault();
      const name = e.target.name.value.trim();
      if (!name) return;
      document.getElementById("dialog-folder").close();
      try {
        await createFolder(name);
      } catch (err) {
        setStatus("error", err.message || "创建失败");
      }
    });

    document.getElementById("btn-new-page").addEventListener("click", function () {
      document.getElementById("form-page").reset();
      document.getElementById("dialog-page").showModal();
    });

    document.getElementById("form-page").addEventListener("submit", async function (e) {
      e.preventDefault();
      const title = e.target.title.value.trim();
      const content = e.target.content.value.trim();
      if (!title || !content) return;
      document.getElementById("dialog-page").close();
      try {
        await createPage(title, content);
      } catch (err) {
        setStatus("error", err.message || "创建失败");
      }
    });

    document.getElementById("file-upload").addEventListener("change", async function (e) {
      const file = e.target.files[0];
      e.target.value = "";
      if (!file) return;
      try {
        await uploadFile(file);
      } catch (err) {
        setStatus("error", err.message || "上传失败");
      }
    });

    document.getElementById("btn-github").addEventListener("click", function () {
      const config = getConfig();
      const form = document.getElementById("form-github");
      form.owner.value = config.owner;
      form.repo.value = config.repo;
      form.branch.value = config.branch;
      form.token.value = config.token;
      document.getElementById("dialog-github").showModal();
    });

    document.getElementById("form-github").addEventListener("submit", function (e) {
      e.preventDefault();
      const form = e.target;
      GitHubClient.saveConfig({
        owner: form.owner.value.trim(),
        repo: form.repo.value.trim(),
        branch: form.branch.value.trim() || "main",
        token: form.token.value.trim(),
      });
      document.getElementById("dialog-github").close();
      setStatus("success", "GitHub 配置已保存");
    });

    document.getElementById("btn-test-github").addEventListener("click", async function () {
      const form = document.getElementById("form-github");
      const config = {
        owner: form.owner.value.trim(),
        repo: form.repo.value.trim(),
        branch: form.branch.value.trim() || "main",
        token: form.token.value.trim(),
      };
      if (!config.token) {
        setStatus("error", "请填写 Token");
        return;
      }
      try {
        setStatus("info", "正在测试连接…");
        const repo = await GitHubClient.testConnection(config);
        setStatus("success", "连接成功：" + repo.full_name);
      } catch (err) {
        setStatus("error", err.message || "连接失败");
      }
    });
  }

  async function init() {
    const params = getParams();
    categoryId = params.categoryId;
    folderPath = params.folderPath;

    if (!categoryId || !NoteManifest.CATEGORY_ORDER.includes(categoryId)) {
      window.location.href = "/";
      return;
    }

    setupDialogs();

    try {
      manifest = await NoteManifest.load();
      renderAll();
    } catch (err) {
      document.getElementById("file-list").innerHTML =
        '<li class="file-list-empty">加载失败：' + escapeHtml(err.message) + "</li>";
    }
  }

  document.addEventListener("DOMContentLoaded", init);
})();
