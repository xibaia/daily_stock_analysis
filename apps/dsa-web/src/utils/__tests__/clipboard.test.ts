import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { copyText } from '../clipboard';

describe('copyText', () => {
  beforeEach(() => {
    Object.defineProperty(window, 'isSecureContext', {
      configurable: true,
      value: true,
    });
  });

  afterEach(() => {
    vi.restoreAllMocks();
    document.querySelectorAll('[data-copy-fallback]').forEach((node) => node.remove());
  });

  it('uses the Clipboard API in a secure context', async () => {
    const writeText = vi.fn().mockResolvedValue(undefined);
    Object.defineProperty(navigator, 'clipboard', {
      configurable: true,
      value: { writeText },
    });
    const execCommand = vi.fn();
    Object.defineProperty(document, 'execCommand', {
      configurable: true,
      value: execCommand,
    });

    await copyText('secure text');

    expect(writeText).toHaveBeenCalledWith('secure text');
    expect(execCommand).not.toHaveBeenCalled();
  });

  it('runs the insecure-context fallback synchronously and removes its textarea', async () => {
    Object.defineProperty(window, 'isSecureContext', {
      configurable: true,
      value: false,
    });
    const writeText = vi.fn();
    Object.defineProperty(navigator, 'clipboard', {
      configurable: true,
      value: { writeText },
    });
    const execCommand = vi.fn(() => true);
    Object.defineProperty(document, 'execCommand', {
      configurable: true,
      value: execCommand,
    });

    const result = copyText('fallback text');

    expect(execCommand).toHaveBeenCalledWith('copy');
    expect(writeText).not.toHaveBeenCalled();
    expect(document.querySelector('[data-copy-fallback]')).toBeNull();
    await result;
  });

  it('uses the synchronous fallback when the Clipboard API is unavailable', async () => {
    Object.defineProperty(navigator, 'clipboard', {
      configurable: true,
      value: undefined,
    });
    const execCommand = vi.fn(() => true);
    Object.defineProperty(document, 'execCommand', {
      configurable: true,
      value: execCommand,
    });

    await copyText('legacy text');

    expect(execCommand).toHaveBeenCalledWith('copy');
  });

  it('rejects and cleans up when the fallback reports failure', async () => {
    Object.defineProperty(window, 'isSecureContext', {
      configurable: true,
      value: false,
    });
    Object.defineProperty(document, 'execCommand', {
      configurable: true,
      value: vi.fn(() => false),
    });

    await expect(copyText('cannot copy')).rejects.toThrow('Clipboard copy failed');
    expect(document.querySelector('[data-copy-fallback]')).toBeNull();
  });

  it('does not retry asynchronously rejected Clipboard API calls outside the gesture', async () => {
    const writeText = vi.fn().mockRejectedValue(new Error('permission denied'));
    Object.defineProperty(navigator, 'clipboard', {
      configurable: true,
      value: { writeText },
    });
    const execCommand = vi.fn(() => true);
    Object.defineProperty(document, 'execCommand', {
      configurable: true,
      value: execCommand,
    });

    await expect(copyText('secure text')).rejects.toThrow('permission denied');
    expect(execCommand).not.toHaveBeenCalled();
  });
});
