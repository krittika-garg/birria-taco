# birria-taco: where we are

*Daniel Enriquez · November 10, 2026*

birria-taco is an app for keeping track of the restaurants you've been to,
ranking them against each other, and deciding with friends where to eat next.
Right now it's a working backend with no app on top of it yet. This is a
plain-language summary of what's built, what's close, and what's missing.

## At a glance

| Feature | Status |
|---|---|
| Accounts and staying logged in | Done |
| Your personal restaurant list | Done |
| Finding places by location and neighborhood | Done |
| Ranking places ("which was better?") | In review |
| Searching your list and a want-to-try list | In review |
| Group plans with friends | Partly done |
| Scores, leaderboards, following, a friends feed | Planned |
| The app itself (screens) | Not started |

## What works today

**Accounts.** You can sign up, log in, and stay logged in without retyping
your password, and log out when you're done.

**Your restaurant list.** You can save restaurants you've eaten at with a
cuisine, notes, and a 0–10 rating, then edit or remove them. Your list is
private to you and sorted best first. You can narrow it down by cuisine.

**Location.** Each saved restaurant knows where it is and which NYC
neighborhood it's in. You can ask for your saved places near where you are
right now, and browse neighborhoods borough by borough.

**Groups.** You can start a group, send friends an invite link, and see who's
in. Groups clean themselves up after two hours, since they're meant for
"where are we eating tonight," not long-term planning. Members can leave.

## Almost there

**Ranking.** This is the core of the app. Instead of picking a number, you
add a place by answering "was it better or worse than this one?" a few times,
and it slots into your list. You first say whether you liked it, thought it
was fine, or didn't like it. It's built and in review.

**Search and want-to-try.** Search your list by name, filter by cuisine and
minimum rating, and save places you want to try before you've been. This is
my piece, and it's in review.

## What's missing

- **No shared restaurant list.** Every saved restaurant belongs to one person,
  so the app can't yet tell that two friends both went to the same place. A lot
  of the social features depend on fixing this.
- **No restaurants to start with.** New users begin with an empty list and
  have to type everything in. We plan to load NYC restaurants from an open
  dataset.
- **Ratings and rankings aren't connected.** A place's spot in your ranked
  list doesn't turn into a score yet.
- **Groups can't decide anything.** You can gather people, but the app doesn't
  suggest places or let anyone vote.
- **Nothing social.** No following people, no feed of what friends ranked.
- **No app.** Everything is tested through the developer API page and the
  test suite. Nobody outside the team can use it yet.

## Who's on what

The team filed the next round of work today:

- **Matthew:** group suggestions near a fair midpoint, neighborhood leaderboard
- **Sihan:** ranking (in review), personal scores, group voting
- **Anuraghav:** following and followers
- **Krittika:** friends feed, a database cleanup
- **Daniel:** search and want-to-try (in review), loading NYC restaurants

What comes after this is in [next-steps.md](next-steps.md).
