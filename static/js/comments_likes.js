(async function(){
  async function j(url, opts={}) {
    const r = await fetch(url, { headers:{'Content-Type':'application/json'}, credentials:'same-origin', ...opts });
    const data = await r.json().catch(()=>({}));
    return { ok:r.ok, status:r.status, data };
  }
  function esc(s){ return String(s).replace(/[&<>]/g,c=>({ '&':'&amp;','<':'&lt;','>':'&gt;' }[c])); }

  async function loadLikes(row){
    const url = row.dataset.likesUrl;
    const cnt = row.querySelector('[data-like-count]');
    const {ok,data} = await j(url);
    if(ok && cnt) cnt.textContent = data.count ?? 0;
    row.querySelector('[data-like-btn]')?.addEventListener('click', async e => { e.preventDefault(); await j(url,{method:'POST'}); loadLikes(row); });
    row.querySelector('[data-unlike-btn]')?.addEventListener('click', async e => { e.preventDefault(); await j(url,{method:'DELETE'}); loadLikes(row); });
  }

  async function loadComments(block){
    const url = block.dataset.commentsUrl;
    const list = block.querySelector('[data-comments-list]');
    const {ok,data} = await j(url);
    if(!ok){ list.innerHTML = '<p class="muted">Failed to load comments.</p>'; return; }
    const items = (data.src||[]).map(c=>`<p><b>${esc(c.author?.displayName||'')}</b>: ${esc(c.comment||'')}</p>`).join('') || '<p class="muted">No comments yet.</p>';
    list.innerHTML = items;
  }
  function hookForm(block){
    const form = block.querySelector('[data-comment-form]');
    if(!form) return;
    form.addEventListener('submit', async e=>{
      e.preventDefault();
      const text = form.comment.value.trim();
      if(!text) return;
      const url = block.dataset.commentsUrl;
      const r = await j(url, { method:'POST', body: JSON.stringify({ type:'comment', comment:text, contentType:'text/plain' }) });
      if(r.ok){ form.reset(); loadComments(block); }
      else if(r.status===403){ alert('Login required to comment.'); }
    });
  }

  document.querySelectorAll('[data-likes-url]').forEach(loadLikes);
  document.querySelectorAll('[data-comments-url]').forEach(block => { loadComments(block); hookForm(block); });
})();
