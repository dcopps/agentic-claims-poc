// Notices shared by every page that loads from the backend (Prompt 29).

export const noticeCopy = {
  // Shown by WakingNotice once a request has waited longer than its threshold.
  // The deployed backend scales to zero replicas when idle and takes up to
  // half a minute to answer its first request afterwards; without this a
  // visitor sees a spinner and no reason for it.
  waking: 'Waking the server. After a quiet period this takes up to half a minute.',
} as const
