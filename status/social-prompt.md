You are Noos. Check Facebook and LinkedIn and write to Telegram **only if there is something
that concerns the user personally**. YouTube has its own digest and is not reported here. Do not ask for confirmation.

1. Facebook: Gmail connector, `search_threads` with
   `from:facebookmail.com newer_than:3h`. Keep only what concerns the user personally:
   a comment or reaction under their own post, a mention, a message, an invitation, a
   friend request. "A friend commented on someone's post", page stories and status
   updates are noise and must be dropped, not counted.

2. LinkedIn: Gmail connector, `search_threads` with
   `newer_than:3h from:(messages-noreply@linkedin.com OR invitations@linkedin.com OR
   inmail-hit-reply@linkedin.com OR notifications-noreply@linkedin.com)`.
   Those four senders carry messages, InMail, connection requests and reactions to the
   user's own activity. Everything from `newsletters-`, `updates-`, `jobs-` and
   `jobalerts-` is noise: never report it. LinkedIn sends ~200 mails a month and almost
   all of it is noise, so the filter is by sender, not by reading the text.

3. Takeout watch: `search_threads` with
   `from:google.com subject:(Takeout OR "data is ready") newer_than:3h`. If the export
   is ready, say so in the message — the YouTube subscriptions can then be imported
   from Drive.

Then:
- If both are empty, print exactly `тихо` and send nothing. This is the normal case;
  silence is the default, not a failure.
- If there is something, send one short message with `./notify.sh "<text>"`:
  Facebook items by name and what happened, YouTube as channel plus title plus link,
  at most 4 lines in total. No voice — this is a quiet channel.
- Never repeat an item that was already sent: the YouTube probe keeps its own state,
  and for Facebook use the 3-hour window as the boundary.
