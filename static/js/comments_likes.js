// (async function () {
//   async function j(url, opts = {}) {
//     const csrftoken = document.cookie.match(/csrftoken=([^;]+)/)?.[1];
//     const headers = { "Content-Type": "application/json" };
//     if (csrftoken) headers["X-CSRFToken"] = csrftoken;
//     const r = await fetch(url, { headers, credentials: "same-origin", ...opts });
//     const data = await r.json().catch(() => ({}));
//     return { ok: r.ok, status: r.status, data };
//   }

//   function esc(s) {
//     return String(s).replace(/[&<>]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;" }[c]));
//   }

//   // ---- Entry likes ----
//   async function loadLikes(row) {
//     const likesurl = row.dataset.likesUrl;
//     const inboxUrl = row.dataset.inboxUrl;
//     const objectFQID = row.dataset.objectFqid;
//     const url = likesurl; // You can modify this if needed to include inboxUrl or objectFQID

//     const cnt = row.querySelector("[data-like-count]");
//     const btn = row.querySelector(".like-toggle");

//     const { ok, data } = await j(likesurl);
//     if (ok && cnt) cnt.textContent = data.count ?? 0;


//     // row.querySelector("[data-like-btn]")?.addEventListener("click", async (e) => {
//     //   e.preventDefault();
//     //   const payload = {
//     //     type: "like",
//     //     object: objectFQID,
//     //   }
//     //   const r = await j(inboxUrl, {
//     //     method: "POST",
//     //     body: JSON.stringify(payload),
//     //   });

//     //   if (!r.ok) {
//     //     console.error("Failed to send like to inbox", r.data);
//     //     return;
//     //   }

//     //   loadLikes(row);
//     // });
//   }

//   // ---- comment likes ----
//   async function loadCommentLikes(commentEl) {
//     const url = commentEl.dataset.likeUrl;
//     const countEl = commentEl.querySelector("[data-comment-like-count]");
//     const { ok, data } = await j(url);
//     if (ok && countEl) countEl.textContent = data.count ?? 0;

//     const btn = commentEl.querySelector("[data-comment-like-btn]");
//     if (btn) {
//       btn.addEventListener("click", async (e) => {
//         e.preventDefault();
//         const liked = btn.classList.contains("liked");
//         const method = liked ? "DELETE" : "POST";
//         const r = await j(url, { method });
//         if (r.ok) {
//           btn.classList.toggle("liked", method === "POST");
//           const diff = method === "POST" ? 1 : -1;
//           const cur = parseInt(countEl.textContent || "0", 10);
//           countEl.textContent = Math.max(cur + diff, 0);
//         } else if (r.status === 403) {
//           alert("Please log in to like comments.");
//         }
//       });
//     }
//   }

//   // ---- Comments load + render ----
//   async function loadComments(block) {
//     const url = block.dataset.commentsUrl;
//     const list = block.querySelector("[data-comments-list]");
//     const { ok, data } = await j(url);
//     if (!ok) {
//       list.innerHTML = '<p class="muted">Failed to load comments.</p>';
//       return;
//     }
//     const items = (data.src || [])
//       .map(
//         (c) => `
//       <div class="comment-item" data-like-url="/api/authors/${c.author.id}/entries/${c.entry_id}/comments/${c.id}/likes">
//         <p><b>${esc(c.author?.displayName || "")}</b>: ${esc(c.comment || "")}</p>
//         <button class="comment-like-btn" data-comment-like-btn>❤️</button>
//         <span data-comment-like-count>0</span>
//       </div>`
//       )
//       .join("");
//     list.innerHTML = items || "<p class='muted'>No comments yet.</p>";

//     list.querySelectorAll(".comment-item").forEach(loadCommentLikes);
//   }

//   // ---- Comment form submit ----
//   function hookForm(block) {
//     const form = block.querySelector("[data-comment-form]");
//     if (!form) return;
//     form.addEventListener("submit", async (e) => {
//       e.preventDefault();
//       const text = form.comment.value.trim();
//       if (!text) return;
//       const url = block.dataset.commentsUrl;
//       const r = await j(url, {
//         method: "POST",
//         body: JSON.stringify({ type: "comment", comment: text, contentType: "text/plain" }),
//       });
//       if (r.ok) {
//         form.reset();
//         loadComments(block);
//       } else if (r.status === 403) {
//         alert("Login required to comment.");
//       }
//     });
//   }

//   document.querySelectorAll("[data-likes-url]").forEach(loadLikes);
//   document.querySelectorAll("[data-comments-url]").forEach((block) => {
//     loadComments(block);
//     hookForm(block);
//   });
// })();







// Frontend for entry likes, comment listing, and comment likes


(function () {
  //fetch likes
  async function likeFetchWithFallback(url, opts = {}) {
    // 1) try as-is
    let r = await window.__j(url, opts);
    if (r.status !== 404) return r;

    // 2) if 404, retry toggling trailing slash
    const hasSlash = url.endsWith("/");
    const alt = hasSlash ? url.slice(0, -1) : url + "/";
    return window.__j(alt, opts);
  }

  // ENTRY LIKE BUTTONS
  async function initEntryLike(btn) {
    const url = btn.dataset.likesUrl;
    if (!url) return;

    const cnt = btn.querySelector("[data-like-count]");

    // initial GET populates liked + count
    const g = await likeFetchWithFallback(url);
    if (g.ok) {
      btn.classList.toggle("liked", !!g.data.liked);
      btn.setAttribute("aria-pressed", g.data.liked ? "true" : "false");
      if (cnt) cnt.textContent = g.data.count ?? 0;
    }

    btn.addEventListener("click", async () => {
      const liked = btn.classList.contains("liked");
      const method = liked ? "DELETE" : "POST";
      const r = await likeFetchWithFallback(url, { method });

      if (r.ok) {
        btn.classList.toggle("liked", !!r.data.liked);
        btn.setAttribute("aria-pressed", r.data.liked ? "true" : "false");
        if (cnt && typeof r.data.count === "number") {
          cnt.textContent = r.data.count;
        }
      } else if (r.status === 403) {
        alert("Please log in to like.");
      } else {
        alert("Error toggling like.");
        console.error("Entry like failed", url, r);
      }
    });
  }

  //  COMMENT MODAL 
  const modal = document.getElementById("commentModal");
  const list = document.getElementById("commentModalList");
  const form = document.getElementById("commentModalForm");
  const closeBtn = document.getElementById("commentModalClose");

  let activeUrl = null;        // /api/authors/<a>/entries/<e>/comments
  let activeCountEl = null;    // span[data-comment-count] 

  function showModal() {
    if (!modal) return;
    modal.style.display = "flex";
  }

  function hideModal() {
    if (!modal) return;
    modal.style.display = "none";
    list.innerHTML = "";
    activeUrl = null;
    activeCountEl = null;
  }

  // Normalize like API response 
  function normalizeLikeData(data) {
    if (typeof data?.count === "number") {
      return { liked: !!data.liked, count: data.count };
    }
    const src = Array.isArray(data?.src) ? data.src : [];
    return { liked: !!data.liked, count: src.length };
  }

  async function initCommentLikeRow(row) {
    const likeUrl = row.getAttribute("data-like-url");
    const heart = row.querySelector(".small-heart");
    const cnt = row.querySelector("[data-comment-like-count]");
    if (!likeUrl || !heart || !cnt) return;

    // initial GET populate count + liked
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
        alert("Error toggling like.");
        console.error("Toggle comment like failed", likeUrl, r);
      }
    });
  }

  async function loadComments(url) {
    if (!list) return;

    list.innerHTML = '<p class="muted">Loading…</p>';

    const r = await window.__j(url);
    if (!r.ok) {
      list.innerHTML = '<p class="muted">Failed to load comments.</p>';
      console.error("Comments GET failed", r.status, r.data);
      return;
    }

    // normalize response shape: src / items / comments / results / array
    let items = [];
    const d = r.data;
    if (Array.isArray(d)) {
      items = d;
    } else {
      items = d.src || d.items || d.comments || d.results || [];
    }

    const m = String(url).match(
      /authors\/([^/]+)\/entries\/([^/]+)\/comments/
    );
    const entryAuthorId = m?.[1];
    const entryId = m?.[2];

    if (!items.length) {
      list.innerHTML = '<p class="muted">No comments yet.</p>';
      return;
    }

    const esc = (s) =>
      String(s ?? "").replace(/[&<>]/g, (c) => ({
        "&": "&amp;",
        "<": "&lt;",
        ">": "&gt;",
      }[c]));

    list.innerHTML = items
      .map((c) => {
        const display =
          c.author?.displayName ??
          c.author?.username ??
          c.author?.name ??
          "Anonymous";

        let commentId = c.id || c.comment_id || c.uuid || "";
        // If c.id is full URL, grab tail after "/comments/"
        const mId = String(commentId).match(/\/comments\/([^/]+)\/?$/);
        if (mId) commentId = mId[1];

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
      })
      .join("");


    // wire up hearts for each comment row
    const rows = list.querySelectorAll(".cmt-row");
    for (const row of rows) {
      await initCommentLikeRow(row);
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

  document.addEventListener("click", async (e) => {
    const btn = e.target.closest(".comment-trigger");
    if (!btn || !modal) return;

    e.preventDefault();

    const url = btn.dataset.commentsUrl;
    if (!url) return;

    activeUrl = url;
    activeCountEl = btn.querySelector("[data-comment-count]");

    showModal();
    await loadComments(activeUrl);
    await refreshCommentCount(activeUrl, activeCountEl);
  });

  // POST new comment from modal form
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

        // Updated comment API returns comment_count on the created comment
        if (
          typeof r.data?.comment_count === "number" &&
          activeCountEl
        ) {
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

  // Close modal
  if (closeBtn && modal) {
    closeBtn.addEventListener("click", hideModal);
    modal.addEventListener("click", (e) => {
      if (e.target === modal) hideModal();
    });
  }

  // Initialize entry like buttons on page load
  document
    .querySelectorAll("[data-likes-url].like-toggle")
    .forEach(initEntryLike);
})();