/** Format prose durations without changing source measurements or code examples. */
export function formatChatDurations(text: string): string {
  return text.split(/(```[\s\S]*?```|`[^`]*`|https?:\/\/\S+)/g).map((part, index) => {
    if (index % 2) return part;
    return part.replace(/(?<![\w.\-:])(\d+(?:\.\d+)?)(?:\s+|[-–‑])(?:seconds?|secs?|s)\b(?!\s*\/)/gi, (original, raw: string) => {
      const seconds = Number(raw);
      if (!Number.isFinite(seconds) || seconds < 60) return original;
      const whole = Math.floor(seconds);
      const fraction = raw.includes('.') ? raw.slice(raw.indexOf('.')).replace(/0+$/, '').replace(/\.$/, '') : '';
      const minutes = Math.floor(whole / 60);
      const tail = `${String(whole % 60).padStart(2, '0')}${fraction}`;
      return whole >= 3600
        ? `${Math.floor(whole / 3600)}:${String(minutes % 60).padStart(2, '0')}:${tail}`
        : `${minutes}:${tail}`;
    });
  }).join('');
}
