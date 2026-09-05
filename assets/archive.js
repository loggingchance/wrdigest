(() => {
  const list = document.querySelector('[data-archive-list]');
  if (!list) return;

  fetch('/data/issues.json', { cache: 'no-store' })
    .then(response => {
      if (!response.ok) throw new Error('Could not load issue index.');
      return response.json();
    })
    .then(issues => {
      list.innerHTML = '';
      issues.forEach(issue => {
        const article = document.createElement('article');
        article.className = 'archive-item';
        article.innerHTML = `
          <time datetime="${issue.date}">${issue.displayDate}</time>
          <h2><a href="${issue.url}">${issue.displayDate}</a></h2>
          <a class="archive-link" href="${issue.url}">Read edition →</a>
          <p>${issue.summary}</p>
        `;
        list.appendChild(article);
      });
    })
    .catch(() => {
      list.innerHTML = '<p>The archive index could not be loaded. Please try again shortly.</p>';
    });
})();
