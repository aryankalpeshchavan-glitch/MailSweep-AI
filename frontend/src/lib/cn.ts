/** Tiny `classnames`-style helper. */
export function cn(...parts: Array<string | false | null | undefined>): string {
  return parts.filter(Boolean).join(" ");
}

/** Join a list of words for a sentence (for accessible labels/alt text). */
export function joinWords(words: Array<string | null | undefined>): string {
  return words.filter(Boolean).join(", ");
}