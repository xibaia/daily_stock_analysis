function copyWithExecCommand(text: string): void {
  const textarea = document.createElement('textarea');
  textarea.value = text;
  textarea.readOnly = true;
  textarea.dataset.copyFallback = 'true';
  textarea.style.position = 'fixed';
  textarea.style.inset = '-9999px auto auto -9999px';
  textarea.style.opacity = '0';
  document.body.appendChild(textarea);

  try {
    textarea.focus();
    textarea.select();
    if (typeof document.execCommand !== 'function' || !document.execCommand('copy')) {
      throw new Error('Clipboard copy failed');
    }
  } finally {
    textarea.remove();
  }
}

export function copyText(text: string): Promise<void> {
  if (window.isSecureContext !== false && navigator.clipboard?.writeText) {
    return navigator.clipboard.writeText(text);
  }

  try {
    copyWithExecCommand(text);
    return Promise.resolve();
  } catch (error) {
    return Promise.reject(error);
  }
}
