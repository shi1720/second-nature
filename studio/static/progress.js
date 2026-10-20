'use strict';
// The renderer reports work in this invocation, including resumed render batches.
// Never infer a percentage from wall-clock time or a bare frame number.
function parseRenderProgress(log) {
  if (typeof log !== 'string') return null;
  let latest = null;
  for (const line of log.split(/\r?\n/)) {
    if (!line.startsWith('FRAME_DONE ')) continue;
    try {
      const report = JSON.parse(line.slice('FRAME_DONE '.length));
      if (!report || typeof report !== 'object' || Array.isArray(report)) continue;
      const {frame, completed, remaining} = report;
      const total = completed + remaining;
      if (Number.isSafeInteger(frame) && frame > 0 &&
          Number.isSafeInteger(completed) && completed >= 0 &&
          Number.isSafeInteger(remaining) && remaining >= 0 &&
          Number.isSafeInteger(total) && total > 0) {
        latest = {value: completed, max: total};
      }
    } catch (_) {
      // A partial or malformed process-output line must not break the dashboard.
    }
  }
  if (latest) return latest;
  for (const match of log.matchAll(/(?:frame|fra)[ :]+(\d+)\s*(?:\/|of)\s*(\d+)/gi)) {
    const value = Number(match[1]), max = Number(match[2]);
    if (Number.isSafeInteger(value) && Number.isSafeInteger(max) && value >= 0 && max > 0 && value <= max) {
      latest = {value, max};
    }
  }
  return latest;
}
if (typeof module !== 'undefined' && module.exports) module.exports = {parseRenderProgress};
