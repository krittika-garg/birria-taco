# birria-taco: next steps

*Daniel Enriquez · November 10, 2026*

Where we go from here. The backend is far enough along that the next big
step is an app people can actually use. Everything below is a direction,
not a fixed plan. For what exists today, see [current-state.md](current-state.md).

## The goal for this stretch

Get to a first version someone outside the team could pick up and use:
sign up, add a few places they've been, rank them, and plan dinner with a
friend.

## 1. Finish the core

- **Ship ranking and search.** Both are in review. Ranking is the heart of
  the app, so it comes first.
- **Turn rankings into scores.** Where a place lands in your list should give
  it a score out of 10. That's the number people will see everywhere.
- **Give people restaurants to start with.** Load NYC restaurants from an open
  dataset so new users can search and tap instead of typing every place in.
  This also means one shared record per restaurant, which the social features
  need.

## 2. Make it social

- **Neighborhood leaderboards.** The best places in each neighborhood,
  according to everyone's rankings.
- **Follow friends.** And see a feed of what they've been ranking lately.
- **Decide as a group.** Each person in a group shares where they are, the app
  suggests places that are fair for everyone, and the group votes.

## 3. Build the app

This is the biggest open piece, and the one we should start talking about now.

**Decisions to make as a team**
- **Phone first, desktop second?** Most people will use this at a restaurant or
  on the way to one, so the phone experience should lead.
- **What it looks like.** Put two or three design directions side by side and
  pick one together before building screens. It should feel social and
  personal, not like a review site: you should be able to tell whose list
  you're looking at.
- **What we build it with.** Something everyone on the team can work in.

**First screens**
1. Sign up and log in
2. My list: search, filter, and want-to-try
3. Add a place
4. The "which was better?" ranking flow
5. Places near me
6. Start a group and invite friends

**Things to get right**
- **Ranking has to feel quick.** It's the thing people do most: tap one of two
  places, a few times, done. We should prototype it before anything else.
- **The first visit can't feel empty.** Until the NYC restaurants are loaded,
  a new user has nothing to look at, so the empty screens need care.
- **Staying logged in should be invisible.** The app should never kick someone
  out mid-ranking.

**Later:** leaderboards, group suggestions and voting, profiles, the friends feed.

## Open questions

- Should a manual rating still exist once scores come from rankings?
- How public are lists? Everyone, only followers, or only you?
- Is this NYC only for now, or do we plan for other cities from the start?
