(function () {
  function escapeHtml(text) {
    return String(text)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function inlineFormat(text) {
    return escapeHtml(text)
      .replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>")
      .replace(/\*(.+?)\*/g, "<em>$1</em>")
      .replace(/`([^`]+)`/g, "<code>$1</code>");
  }

  function markdownToHtml(md) {
    const lines = md.replace(/\r\n/g, "\n").split("\n");
    const html = [];
    let inCode = false;
    let codeLines = [];
    let listType = null;

    function closeList() {
      if (listType) {
        html.push(listType === "ul" ? "</ul>" : "</ol>");
        listType = null;
      }
    }

    for (let i = 0; i < lines.length; i++) {
      const line = lines[i];

      if (line.startsWith("```")) {
        if (inCode) {
          html.push(
            "<pre><code>" + escapeHtml(codeLines.join("\n")) + "</code></pre>"
          );
          codeLines = [];
          inCode = false;
        } else {
          closeList();
          inCode = true;
        }
        continue;
      }

      if (inCode) {
        codeLines.push(line);
        continue;
      }

      if (!line.trim()) {
        closeList();
        continue;
      }

      const heading = line.match(/^(#{1,3})\s+(.+)$/);
      if (heading) {
        closeList();
        const level = heading[1].length + 1;
        html.push(
          "<h" + level + ">" + inlineFormat(heading[2]) + "</h" + level + ">"
        );
        continue;
      }

      if (line.startsWith("> ")) {
        closeList();
        html.push("<blockquote>" + inlineFormat(line.slice(2)) + "</blockquote>");
        continue;
      }

      const ul = line.match(/^[-*]\s+(.+)$/);
      if (ul) {
        if (listType !== "ul") {
          closeList();
          listType = "ul";
          html.push("<ul>");
        }
        html.push("<li>" + inlineFormat(ul[1]) + "</li>");
        continue;
      }

      const ol = line.match(/^\d+\.\s+(.+)$/);
      if (ol) {
        if (listType !== "ol") {
          closeList();
          listType = "ol";
          html.push("<ol>");
        }
        html.push("<li>" + inlineFormat(ol[1]) + "</li>");
        continue;
      }

      closeList();
      html.push("<p>" + inlineFormat(line) + "</p>");
    }

    closeList();
    if (inCode && codeLines.length) {
      html.push(
        "<pre><code>" + escapeHtml(codeLines.join("\n")) + "</code></pre>"
      );
    }

    return html.join("\n");
  }

  window.markdownToHtml = markdownToHtml;
})();
