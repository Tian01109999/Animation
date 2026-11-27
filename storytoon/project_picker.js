() => {
  if (globalThis.storytoonProjectPicker) return;
  globalThis.storytoonProjectPicker = true;
  let scheduled = false;
  function decorate() {
    scheduled = false;
    const picker = document.getElementById('project-picker');
    if (!picker) return;
    picker.querySelectorAll('[role="option"]').forEach(option => {
      if (option.querySelector('.project-trash')) return;
      const name = option.getAttribute('aria-label');
      if (!name) return;
      const button = document.createElement('button');
      button.type = 'button';
      button.className = 'project-trash';
      button.setAttribute('aria-label', 'Xóa project ' + name);
      button.title = 'Xóa project ' + name;
      button.innerHTML = '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M3 6h18M9 6V4h6v2M5 6l1 14h12l1-14M10 10v6M14 10v6"/></svg>';
      button.addEventListener('pointerdown', e => { e.preventDefault(); e.stopPropagation(); });
      button.addEventListener('mousedown', e => { e.preventDefault(); e.stopPropagation(); });
      button.addEventListener('click', e => {
        e.preventDefault(); e.stopImmediatePropagation();
        globalThis.storytoonDeletePayload = JSON.stringify({name, nonce: Date.now()});
        const trigger = document.getElementById('project-delete-trigger');
        if (!trigger) return;
        trigger.click();
        const input = picker.querySelector('[role="combobox"]');
        if (input) input.dispatchEvent(new KeyboardEvent('keydown', {key: 'Escape', code: 'Escape', bubbles: true}));
      });
      option.appendChild(button);
    });
  }
  new MutationObserver(() => {
    if (!scheduled) { scheduled = true; requestAnimationFrame(decorate); }
  }).observe(document.body, {childList: true, subtree: true});
  decorate();
}
