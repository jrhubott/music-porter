import chalk from 'chalk';

const BYTES_PER_KB = 1024;
const BYTES_PER_MB = 1024 * 1024;
const BYTES_PER_GB = 1024 * 1024 * 1024;
const MS_PER_SECOND = 1000;

/** Format bytes into human-readable string. */
export function formatBytes(bytes: number): string {
  if (bytes >= BYTES_PER_GB) return `${(bytes / BYTES_PER_GB).toFixed(1)} GB`;
  if (bytes >= BYTES_PER_MB) return `${(bytes / BYTES_PER_MB).toFixed(1)} MB`;
  if (bytes >= BYTES_PER_KB) return `${(bytes / BYTES_PER_KB).toFixed(1)} KB`;
  return `${bytes} B`;
}

/** Format duration in milliseconds to human-readable. */
export function formatDuration(ms: number): string {
  const seconds = Math.round(ms / MS_PER_SECOND);
  if (seconds < 60) return `${seconds}s`;
  const minutes = Math.floor(seconds / 60);
  const secs = seconds % 60;
  return `${minutes}m ${secs}s`;
}

/** Print a simple table. */
export function printTable(headers: string[], rows: string[][]): void {
  const widths = headers.map((h, i) => {
    const maxDataWidth = rows.reduce((max, row) => Math.max(max, (row[i] ?? '').length), 0);
    return Math.max(h.length, maxDataWidth);
  });

  const headerLine = headers.map((h, i) => h.padEnd(widths[i]!)).join('  ');
  const separator = widths.map((w) => '─'.repeat(w)).join('──');

  console.log(chalk.bold(headerLine));
  console.log(chalk.dim(separator));
  for (const row of rows) {
    console.log(row.map((cell, i) => cell.padEnd(widths[i]!)).join('  '));
  }
}

/** Print a labeled value. */
export function printField(label: string, value: string): void {
  console.log(`  ${chalk.dim(label + ':')} ${value}`);
}

/** Print a success message. */
export function printSuccess(message: string): void {
  console.log(chalk.green(`  ${message}`));
}

/** Print an error message. */
export function printError(message: string): void {
  console.error(chalk.red(`Error: ${message}`));
}

/** Print a warning message. */
export function printWarning(message: string): void {
  console.log(chalk.yellow(`Warning: ${message}`));
}
