
(function () {
  // ---- one-time guard ----
  if (window.__COMMENT_MODAL_BOUND__) return;
  window.__COMMENT_MODAL_BOUND__ = true;

  // ---- fetch helpers ----
  function getCookie(name) {
    const m = document.cookie.match(new RegExp("(^|; )" + name + "=([^;]*)"));
    return m ? decodeURIComponent(m[2]) : null;
  }

  // Use existing window.__j if present; otherwise define it
  if (typeof window.__j !== "function") {
    window.__j = async function (url, opts = {}) {
      const headers = { "Content-Type": "application/json", ...(opts.headers || {}) };
      const csrftoken = getCookie("csrftoken");
      if (csrftoken) headers["X-CSRFToken"] = csrftoken;
      const r = await fetch(url, { credentials: "same-origin", headers, ...opts });
      let data = {};
      try { data = await r.json(); } catch (e) {}
      return { ok: r.ok, status: r.status, data };
    };
  }

  async function likeFetchWithFallback(url, opts = {}) {
    // 1) try as-is
    let r = await window.__j(url, opts);
    if (r.status !== 404) return r;
    // 2) retry with/without trailing slash
    const hasSlash = url.endsWith("/");
    const alt = hasSlash ? url.slice(0, -1) : url + "/";
    return window.__j(alt, opts);
  }

  // ---- DOM refs ----
  const modal = document.getElementById("commentModal");
  const list  = document.getElementById("commentModalList");
  const form  = document.getElementById("commentModalForm");
  const closeBtn = document.getElementById("commentModalClose");

  let activeUrl = null;      // /api/authors/<a>/entries/<e>/comments
  let activeCountEl = null;  // span[data-comment-count] on the trigger

  function showModal() {
    if (!modal) return;
    modal.style.display = "flex";
  }
  function hideModal() {
    if (!modal) return;
    modal.style.display = "none";
    if (list) list.innerHTML = "";
    form?.reset();
    activeUrl = null;
    activeCountEl = null;
  }

  // ---- utilities ----
  function esc(s) {
    return String(s ?? "").replace(/[&<>]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;" }[c]));
  }
  function normalizeLikeData(data) {
    if (typeof data?.count === "number") return { liked: !!data.liked, count: data.count };
    const src = Array.isArray(data?.src) ? data.src : [];
    return { liked: !!data.liked, count: src.length };
  }

  // ---- comment-like row init ----
  async function initCommentLikeRow(row) {
    const likeUrl = row.getAttribute("data-like-url");
    const heart = row.querySelector(".small-heart");
    const cnt = row.querySelector("[data-comment-like-count]");
    if (!likeUrl || !heart || !cnt) return;

    // initial GET
    const g = await likeFetchWithFallback(likeUrl, {});
    if (g.ok) {
      const norm = normalizeLikeData(g.data);
      cnt.textContent = norm.count;
      heart.classList.toggle("liked", norm.liked);
      heart.setAttribute("aria-pressed", norm.liked ? "true" : "false");
    }

    heart.addEventListener("click", async (e) => {
      e.preventDefault();
      const liked = heart.classList.contains("liked");
      const method = liked ? "DELETE" : "POST";
      const r = await likeFetchWithFallback(likeUrl, { method });
      if (r.ok) {
        const norm = normalizeLikeData(r.data);
        heart.classList.toggle("liked", norm.liked);
        heart.setAttribute("aria-pressed", norm.liked ? "true" : "false");
        cnt.textContent = norm.count;
      } else if (r.status === 403) {
        alert("Please log in to like.");
      } else {
        alert("Error toggling like. meow");
        console.error("Toggle comment like failed", likeUrl, r);
      }
    });
  }

  // ---- comments load (with in-flight lock + de-dupe) ----
  let loadingComments = false;

  async function loadComments(url) {
    if (!list || !url) return;
    if (loadingComments) return;    // prevent overlapping loads
    loadingComments = true;

    list.innerHTML = '<p class="muted">Loading…</p>';

    try {
      const r = await window.__j(url);
      if (!r.ok) {
        list.innerHTML = '<p class="muted">Failed to load comments.</p>';
        console.error("Comments GET failed", r.status, r.data);
        return;
      }

      // normalize payload to array
      let items = [];
      const d = r.data;
      if (Array.isArray(d)) items = d;
      else items = d.src || d.items || d.comments || d.results || [];

      // de-duplicate by stable key (id/comment_id/uuid or trailing /comments/<id>)
      const idFrom = (c) => {
        let k = c.id ?? c.comment_id ?? c.uuid ?? "";
        const m = String(k).match(/\/comments\/([^/]+)\/?$/);
        if (m) k = m[1];
        return String(k || "");
      };
      const seen = new Set();
      items = items.filter((c) => {
        const k = idFrom(c);
        if (seen.has(k)) return false;
        seen.add(k);
        return true;
      });

      // derive author/entry ids from URL
      const m = String(url).match(/authors\/([^/]+)\/entries\/([^/]+)\/comments/);
      const entryAuthorId = m?.[1];
      const entryId = m?.[2];

      if (!items.length) {
        list.innerHTML = '<p class="muted">No comments yet.</p>';
        return;
      }

      list.innerHTML = items.map((c) => {
        const display =
          c.author?.displayName ??
          c.author?.username ??
          c.author?.name ??
          "Anonymous";

        // compute commentId (handles full URLs)
        let commentId = c.id ?? c.comment_id ?? c.uuid ?? "";
        const mid = String(commentId).match(/\/comments\/([^/]+)\/?$/);
        if (mid) commentId = mid[1];

        const likeUrl = entryAuthorId && entryId && commentId
          ? `/api/authors/${entryAuthorId}/entries/${entryId}/comments/${commentId}/likes/`
          : "";

        return `
          <div class="cmt-row" ${likeUrl ? `data-like-url="${likeUrl}"` : ""}>
            <div class="cmt-text">
              <b>${esc(display)}</b>: ${esc(c.comment ?? c.text ?? "")}
            </div>
            <div class="cmt-actions">
              <svg class="icon small-heart" xmlns="http://www.w3.org/2000/svg"
                   viewBox="0 0 24 24" fill="none" stroke="currentColor"
                   stroke-width="2" aria-hidden="true" role="button">
                <path stroke-linecap="round" stroke-linejoin="round"
                      d="M21 8.5c0 3.78-3.4 6.86-8.55 11.54L12 21.35
                         11.45 21.04C6.4 17.36 3 14.28 3 10.5
                         3 7.41 5.42 5 8.5 5
                         10.24 5 11.91 5.81 13 7.09
                         14.09 5.81 15.76 5 17.5 5
                         20.58 5 23 7.41 23 10.5z"/>
              </svg>
              <span data-comment-like-count>0</span>
            </div>
          </div>
        `;
      }).join("");

      // wire up like hearts
      const rows = list.querySelectorAll(".cmt-row");
      for (const row of rows) {
        await initCommentLikeRow(row);
      }
    } finally {
      loadingComments = false;
    }
  }

  async function refreshCommentCount(url, el) {
    if (!url || !el) return;
    const r = await window.__j(url);
    if (r.ok) {
      const d = r.data;
      const count =
        typeof d?.count === "number"
          ? d.count
          : Array.isArray(d?.src)
          ? d.src.length
          : 0;
      el.textContent = count;
    }
  }

  // ---- open modal on .comment-trigger (single binding) ----
  document.addEventListener("click", async (e) => {
    const btn = e.target.closest(".comment-trigger");
    if (!btn || !modal) return;

    e.preventDefault();
    const url = btn.dataset.commentsUrl;
    if (!url) return;

    // If already open for the same URL, skip
    if (modal.style.display === "flex" && url === activeUrl) return;

    activeUrl = url;
    activeCountEl = btn.querySelector("[data-comment-count]") || null;

    showModal();
    await loadComments(activeUrl);
    await refreshCommentCount(activeUrl, activeCountEl);
  });

  // ---- submit new comment from modal ----
  if (form) {
    form.addEventListener("submit", async (e) => {
      e.preventDefault();
      if (!activeUrl) return;

      const text = form.comment.value.trim();
      if (!text) return;

      const r = await window.__j(activeUrl, {
        method: "POST",
        body: JSON.stringify({
          type: "comment",
          comment: text,
          contentType: "text/plain",
        }),
      });

      if (r.ok) {
        form.reset();
        await loadComments(activeUrl);
        // Prefer server-returned count if provided
        if (typeof r.data?.comment_count === "number" && activeCountEl) {
          activeCountEl.textContent = r.data.comment_count;
        } else {
          await refreshCommentCount(activeUrl, activeCountEl);
        }
      } else if (r.status === 403) {
        alert("Please log in to comment.");
        console.warn("403 on comment POST", r.data);
      } else {
        alert("Failed to post comment.");
        console.error("Comment POST failed", r.status, r.data);
      }
    });
  }

  // ---- close modal ----
  if (closeBtn && modal) {
    closeBtn.addEventListener("click", hideModal);
    modal.addEventListener("click", (e) => {
      if (e.target === modal) hideModal();
    });
  }
})();
