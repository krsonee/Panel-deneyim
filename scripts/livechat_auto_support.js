// Bizzo LiveChat auto-support helper — paste in LiveChat tab console OR use via browser_cdp
// Usage: sendChatMessage("Merhaba...")

function sendChatMessage(msg) {
  const box = document.querySelector('[contenteditable=true]');
  if (!box) return 'no composer';
  box.focus();
  box.innerHTML = '';
  document.execCommand('insertText', false, msg);
  box.dispatchEvent(new InputEvent('input', { bubbles: true }));
  const send = [...document.querySelectorAll('button')].find(
    (b) => b.textContent.trim() === 'Send' && !b.disabled
  );
  if (send) {
    send.click();
    return 'sent';
  }
  return 'send disabled';
}

function getChatSnapshot() {
  const t = document.body.innerText;
  const active = (t.match(/My chats \((\d+)\)/) || [])[1];
  const lastCustomer = [...document.querySelectorAll('[class*="message"], [data-testid*="message"]')]
    .map((el) => el.innerText?.trim())
    .filter(Boolean)
    .slice(-5);
  return { activeChats: active, url: location.href, preview: t.slice(0, 3000), lastCustomer };
}

// export for CDP: getChatSnapshot() / sendChatMessage("...")
