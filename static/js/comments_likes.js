(async function () {
  async function j(url, opts = {}) {
    const csrftoken = document.cookie.match(/csrftoken=([^;]+)/)?.[1];
    const headers = { "Content-Type": "application/json" };
    if (csrftoken) headers["X-CSRFToken"] = csrftoken;
    const r = await fetch(url, { headers, credentials: "same-origin", ...opts });
    const data = await r.json().catch(() => ({}));
    return { ok: r.ok, status: r.status, data };
  }

  function esc(s) {
    return String(s).replace(/[&<>]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;" }[c]));
  }

  // ---- Entry likes ----
  async function loadLikes(row) {
    const url = row.dataset.likesUrl;
    const cnt = row.querySelector("[data-like-count]");
    const { ok, data } = await j(url);
    if (ok && cnt) cnt.textContent = data.count ?? 0;
    row.querySelector("[data-like-btn]")?.addEventListener("click", async (e) => {
      e.preventDefault();
      await j(url, { method: "POST" });
      loadLikes(row);
    });
    row.querySelector("[data-unlike-btn]")?.addEventListener("click", async (e) => {
      e.preventDefault();
      await j(url, { method: "DELETE" });
      loadLikes(row);
    });
  }

  // ---- comment likes ----
  async function loadCommentLikes(commentEl) {
    const url = commentEl.dataset.likeUrl;
    const countEl = commentEl.querySelector("[data-comment-like-count]");
    const { ok, data } = await j(url);
    if (ok && countEl) countEl.textContent = data.count ?? 0;

    const btn = commentEl.querySelector("[data-comment-like-btn]");
    if (btn) {
      btn.addEventListener("click", async (e) => {
        e.preventDefault();
        const liked = btn.classList.contains("liked");
        const method = liked ? "DELETE" : "POST";
        const r = await j(url, { method });
        if (r.ok) {
          btn.classList.toggle("liked", method === "POST");
          const diff = method === "POST" ? 1 : -1;
          const cur = parseInt(countEl.textContent || "0", 10);
          countEl.textContent = Math.max(cur + diff, 0);
        } else if (r.status === 403) {
          alert("Please log in to like comments.");
        }
      });
    }
  }

  // ---- Comments load + render ----
  async function loadComments(block) {
    const url = block.dataset.commentsUrl;
    const list = block.querySelector("[data-comments-list]");
    const { ok, data } = await j(url);
    if (!ok) {
      list.innerHTML = '<p class="muted">Failed to load comments.</p>';
      return;
    }
    const items = (data.src || [])
      .map(
        (c) => `
      <div class="comment-item" data-like-url="/api/authors/${c.author.id}/entries/${c.entry_id}/comments/${c.id}/likes">
        <p><b>${esc(c.author?.displayName || "")}</b>: ${esc(c.comment || "")}</p>
        <button class="comment-like-btn" data-comment-like-btn>❤️</button>
        <span data-comment-like-count>0</span>
      </div>`
      )
      .join("");
    list.innerHTML = items || "<p class='muted'>No comments yet.</p>";

    list.querySelectorAll(".comment-item").forEach(loadCommentLikes);
  }

  // ---- Comment form submit ----
  function hookForm(block) {
    const form = block.querySelector("[data-comment-form]");
    if (!form) return;
    form.addEventListener("submit", async (e) => {
      e.preventDefault();
      const text = form.comment.value.trim();
      if (!text) return;
      const url = block.dataset.commentsUrl;
      const r = await j(url, {
        method: "POST",
        body: JSON.stringify({ type: "comment", comment: text, contentType: "text/plain" }),
      });
      if (r.ok) {
        form.reset();
        loadComments(block);
      } else if (r.status === 403) {
        alert("Login required to comment.");
      }
    });
  }

  document.querySelectorAll("[data-likes-url]").forEach(loadLikes);
  document.querySelectorAll("[data-comments-url]").forEach((block) => {
    loadComments(block);
    hookForm(block);
  });
})();
