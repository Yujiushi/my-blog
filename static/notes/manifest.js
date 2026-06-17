(function () {
  const CATEGORY_ORDER = ["life", "academic", "career"];

  function slugify(text) {
    const base = String(text)
      .trim()
      .replace(/\s+/g, "-")
      .replace(/[^\w\u4e00-\u9fff-]/g, "")
      .slice(0, 48);
    return base || "item-" + Date.now();
  }

  function splitPath(folderPath) {
    if (!folderPath) return [];
    return folderPath.split("/").filter(Boolean);
  }

  function getCategory(manifest, categoryId) {
    return manifest.categories && manifest.categories[categoryId];
  }

  function getContainer(manifest, categoryId, folderPath) {
    const category = getCategory(manifest, categoryId);
    if (!category) return null;

    let container = category.children || (category.children = []);
    const parts = splitPath(folderPath);

    for (let i = 0; i < parts.length; i++) {
      const folder = container.find(function (item) {
        return item.type === "folder" && item.slug === parts[i];
      });
      if (!folder) return null;
      if (!folder.children) folder.children = [];
      container = folder.children;
    }

    return container;
  }

  function countPages(children) {
    if (!children) return 0;
    let count = 0;
    children.forEach(function (item) {
      if (item.type === "page") {
        count += 1;
      } else if (item.type === "folder") {
        count += countPages(item.children);
      }
    });
    return count;
  }

  function countItems(children) {
    if (!children) return 0;
    let count = 0;
    children.forEach(function (item) {
      if (item.type === "folder") {
        count += 1 + countItems(item.children);
      } else if (item.type === "page" || item.type === "file") {
        count += 1;
      }
    });
    return count;
  }

  function pageRepoPath(categoryId, folderPath, slug) {
    const parts = ["notes", categoryId];
    splitPath(folderPath).forEach(function (p) {
      parts.push(p);
    });
    parts.push(slug + ".html");
    return parts.join("/");
  }

  function pageHref(categoryId, folderPath, slug) {
    return siteUrl("/" + pageRepoPath(categoryId, folderPath, slug));
  }

  function fileRepoPath(categoryId, folderPath, filename) {
    const parts = ["notes", categoryId];
    splitPath(folderPath).forEach(function (p) {
      parts.push(p);
    });
    parts.push(filename);
    return parts.join("/");
  }

  function fileHref(categoryId, folderPath, filename) {
    return siteUrl("/" + fileRepoPath(categoryId, folderPath, filename));
  }

  function findFile(manifest, categoryId, folderPath, filename) {
    const container = getContainer(manifest, categoryId, folderPath);
    if (!container) return null;
    return container.find(function (item) {
      return item.type === "file" && item.filename === filename;
    });
  }

  function addFile(manifest, categoryId, folderPath, file) {
    const container = getContainer(manifest, categoryId, folderPath);
    if (!container) throw new Error("目录不存在");
    if (findFile(manifest, categoryId, folderPath, file.filename)) {
      throw new Error("同名文件已存在");
    }
    container.unshift({
      type: "file",
      title: file.title,
      filename: file.filename,
      date: file.date,
      search: file.search || file.title,
    });
  }

  function browseHref(categoryId, folderPath) {
    let url = siteUrl("/browse.html") + "?c=" + encodeURIComponent(categoryId);
    if (folderPath) url += "&p=" + encodeURIComponent(folderPath);
    return url;
  }

  function assetDepth(folderPath) {
    return 2 + splitPath(folderPath).length;
  }

  function rootPrefix(folderPath) {
    return "../".repeat(assetDepth(folderPath));
  }

  function flatten(manifest) {
    const results = [];

    function walk(categoryId, category, folderPath, children) {
      (children || []).forEach(function (item) {
        if (item.type === "folder") {
          const childPath = folderPath
            ? folderPath + "/" + item.slug
            : item.slug;
          results.push({
            kind: "folder",
            title: item.name,
            search: item.name + " " + (category.search || ""),
            href: browseHref(categoryId, childPath),
            category: categoryId,
            categoryLabel: category.label,
          });
          walk(categoryId, category, childPath, item.children);
        } else if (item.type === "page") {
          results.push({
            kind: "page",
            title: item.title,
            search: (item.search || item.title) + " " + (category.search || ""),
            href: pageHref(categoryId, folderPath, item.slug),
            date: item.date,
            category: categoryId,
            categoryLabel: category.label,
          });
        }
      });
    }

    CATEGORY_ORDER.forEach(function (categoryId) {
      const category = getCategory(manifest, categoryId);
      if (!category) return;
      walk(categoryId, category, "", category.children);
    });

    return results;
  }

  function findPage(manifest, categoryId, folderPath, slug) {
    const container = getContainer(manifest, categoryId, folderPath);
    if (!container) return null;
    return container.find(function (item) {
      return item.type === "page" && item.slug === slug;
    });
  }

  function findFolder(manifest, categoryId, folderPath, folderSlug) {
    const container = getContainer(manifest, categoryId, folderPath);
    if (!container) return null;
    return container.find(function (item) {
      return item.type === "folder" && item.slug === folderSlug;
    });
  }

  function addFolder(manifest, categoryId, folderPath, name) {
    const container = getContainer(manifest, categoryId, folderPath);
    if (!container) throw new Error("目录不存在");

    const slug = slugify(name);
    if (findFolder(manifest, categoryId, folderPath, slug)) {
      throw new Error("同名文件夹已存在");
    }

    const folder = { type: "folder", name: name.trim(), slug: slug, children: [] };
    container.unshift(folder);
    return folder;
  }

  function addPage(manifest, categoryId, folderPath, page) {
    const container = getContainer(manifest, categoryId, folderPath);
    if (!container) throw new Error("目录不存在");

    if (findPage(manifest, categoryId, folderPath, page.slug)) {
      throw new Error("同名页面已存在");
    }

    container.unshift({
      type: "page",
      title: page.title,
      slug: page.slug,
      date: page.date,
      search: page.search || page.title,
    });
  }

  function today() {
    const d = new Date();
    const m = String(d.getMonth() + 1).padStart(2, "0");
    const day = String(d.getDate()).padStart(2, "0");
    return d.getFullYear() + "-" + m + "-" + day;
  }

  async function load() {
    const res = await fetch(siteUrl("/notes.json") + "?_=" + Date.now());
    if (!res.ok) throw new Error("无法加载 notes.json");
    return res.json();
  }

  function serialize(manifest) {
    return JSON.stringify(manifest, null, 2) + "\n";
  }

  function getBreadcrumb(manifest, categoryId, folderPath) {
    const crumbs = [{ label: "首页", href: siteUrl("/") }];
    const category = getCategory(manifest, categoryId);
    if (!category) return crumbs;

    crumbs.push({
      label: category.emoji + " " + category.label,
      href: browseHref(categoryId, ""),
    });

    let container = category.children || [];
    const parts = splitPath(folderPath);

    parts.forEach(function (slug, index) {
      const folder = container.find(function (item) {
        return item.type === "folder" && item.slug === slug;
      });
      if (!folder) return;
      const pathSoFar = parts.slice(0, index + 1).join("/");
      crumbs.push({
        label: folder.name,
        href: browseHref(categoryId, pathSoFar),
      });
      container = folder.children || [];
    });

    return crumbs;
  }

  window.NoteManifest = {
    CATEGORY_ORDER: CATEGORY_ORDER,
    slugify: slugify,
    splitPath: splitPath,
    getCategory: getCategory,
    getContainer: getContainer,
    countPages: countPages,
    countItems: countItems,
    pageRepoPath: pageRepoPath,
    pageHref: pageHref,
    fileRepoPath: fileRepoPath,
    fileHref: fileHref,
    findFile: findFile,
    addFile: addFile,
    browseHref: browseHref,
    assetDepth: assetDepth,
    rootPrefix: rootPrefix,
    flatten: flatten,
    addFolder: addFolder,
    addPage: addPage,
    today: today,
    load: load,
    serialize: serialize,
    getBreadcrumb: getBreadcrumb,
  };
})();
