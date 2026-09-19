# Minkops — LinkedIn Post Drafts (v2)

Three posts: the founder piece from the first round (kept as-is), plus two new ones swapped in for the two engineering-reel scripts. The brief for the new two was "less engineering, more product-proof" — so both lean on things a stranger can actually verify or watch happen, rather than internal architecture decisions. Nothing here references pricing, named prospects, or claims a paying customer — Minkops is still pre-sale, and the copy is careful not to imply otherwise.

---

## Post 1 — Founder post · Plain text · Company Page
**Format:** plain-text post, no video · **Voice:** founder, first person plural · **Posts well from:** the Minkops company page or a founder's personal profile *(unchanged from the first draft)*

### Full post
> I keep noticing the same instinct in founders I talk to: the moment they want to move faster, their first move is to hire.
>
> We've gone the opposite way. Minkops is under 10 people, and most of us are wearing four or five hats before lunch. What makes that possible isn't hustle — it's that we build the AI employees we're selling before we sell them, and we run our own company on them first.
>
> Right now, that's not a slide in a pitch deck. Imel reads incoming email, classifies it, and drafts the reply before a human opens the inbox. Kall picks up a support ticket, resolves it, and updates the record — no one babysitting a queue. Both run end-to-end, today, inside our own operations, built on the same runtime we'll hand to customers.
>
> The rest of the roster — an agent that qualifies and calls leads, one that manages our social presence, one that just watches the metrics and tells us what needs attention — is exactly what we're building next, for the exact same reason: we needed it before anyone else did.
>
> That's the actual pitch, underneath all of it: hire an AI employee the way you'd hire a person — for a specific role, with real responsibility — except it starts on day one, works nights and weekends, and never asks for a raise.
>
> We built Minkops because a five-person team needs leverage, not headcount. Everything since then has just been making it good enough to hand to someone else.

**Suggested hashtags:** #StartupLife #AIagents #FoundersJourney #SmallTeamBigOutput
**Source:** `README.md` Planned Agents roster (Imel, Kall, Leed, Eko, Floc, Insi); `docs/decisions-log.md` 2026-02-06 entry (Imel + Kall validated end-to-end). Only Imel and Kall are described as working today — the rest are framed as roadmap, not shipped.

---

## Post 2 — NEW · Interactive demo / CTA post · Plain text
**Format:** plain-text post with a link · **Voice:** company, direct-to-prospect · **Goal:** drive traffic to the live agent-recommendation funnel on the Minkops site

### Full post
> Most "AI for your business" pitches ask you to imagine the ROI. We'd rather just show you.
>
> There's a 90-second questionnaire live on the Minkops site right now — four honest questions about where your time actually goes: support tickets, lead follow-up, admin, content, whatever's eating your week. Answer them, and it comes back with a specific answer: which AI agent fits your biggest bottleneck, and roughly how many hours a week it would give back to you.
>
> No sales call required to get that answer. No demo booking, no "let me connect you with someone." Four questions, then a straight answer — because we'd rather you find out in ninety seconds whether this is worth your time than sit through thirty minutes to learn the same thing.
>
> If you've ever thought "I need another person for this, but I can't justify a hire yet" — this is built for exactly that moment. Worst case, it tells you Minkops isn't the right fit yet. Best case, it tells you exactly who to hire next — except this one starts today.
>
> Try it: [link to the funnel on minkops.com]

**Suggested hashtags:** #SmallBusiness #AIforBusiness #Automation #StartupTools
**Source:** `docs/decisions-log.md` 2026-03-27 entry — `QuestionnaireFunnel.tsx`, live on the corporate website, four-step qualification funnel with a conservative hours-recovered estimate and a mapped agent recommendation.

---

## Post 3 — NEW · Reel / short video · "Real, not a mockup"
**Format:** short-form vertical video (Reel), 20–30 sec, screen-recorded terminal + calm voiceover · **Voice:** company, product-credibility angle · **Presenter:** whoever's comfortable narrating over screen capture — doesn't need to be on camera

### Suggested caption (goes with the video)
> We didn't storyboard this. Real terminal, real email, real AI-drafted reply — start to finish, no cuts.

### Script
> A lot of "AI agent" demos you'll see are a slide deck wearing a UI skin. Nothing's actually running underneath it.
>
> So here's the opposite of that. This is Imel — our email agent — handed a customer email it's never seen before. Watch it: it reads the email, works out what the customer actually needs, and drafts a reply. No human touching the keyboard until the review step.
>
> It's not polished. It's not supposed to be. It's supposed to be real — because "real" is the entire point of what we're building. An AI employee that only works in a sizzle reel isn't an employee, it's a prop.
>
> Before any agent we build goes anywhere near a customer, it has to clear one bar: not "does it look convincing in a demo" — "did it actually do the job."

**Suggested hashtags:** #AIagents #ProductProof #NoFluff #Automation
**Source:** `docs/decisions-log.md` 2026-02-06 and 2026-02-08 entries — Imel's classify → draft-reply flow, validated running end-to-end via `run-imel` (with and without the LLM path) in local execution.

---

### Notes for Kartik
- All three now lean on things an outside viewer can verify or try themselves (a live feature, a real screen recording) rather than internal engineering decisions — matches the "product-proof" brief.
- Post 3's screen recording is real work, not just copy: it needs an actual `run-imel` pass captured on screen, ideally with a genuinely unseen sample email so the "never seen before" line in the voiceover stays honest.
- Post 2's link placeholder needs the live funnel URL on minkops.com dropped in before posting.
- Kept the same discipline as the first round: no invented metrics, no implied paying customers, no mention of Matrix JEE Academy, Pradeepraj Infra, or pricing.
