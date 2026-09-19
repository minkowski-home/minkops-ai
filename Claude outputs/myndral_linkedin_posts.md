# Myndral — LinkedIn Post Drafts (v2)

The founder post stays. Both engineering reels are out, replaced with two posts built to make someone stop scrolling and want to know more — pulled straight from the artist bios already live on the corporate website's public catalogue (`apps/corporate-website/src/content/generatedArtistCatalogue.ts`), not invented. Both artists, both backstories, and the exact wording of the "official" bio are already public-facing canon; I only wrote the LinkedIn framing around them.

---

## Post 1 — NEW · Artist spotlight · Carousel / visual post
**Format:** carousel or single striking visual + caption · **Voice:** company/brand · **Goal:** introduce one artist as a hook, drive clicks into the catalogue
**Subject:** ISO-9000

### Suggested caption
> Nobody has ever seen ISO-9000's face. There's a reason for that.

### Full post
> Every artist on Myndral has a story. ISO-9000's is stranger than most.
>
> The official bio: "Digital Material Scientist. A post-gender synthetic entity engineering sound that mimics physical textures." No photos exist. No interviews. Just industrial-grey visuals, a QR code standing in for a face, and a sound built out of things that shouldn't be musical — glass shattering, brushed steel, pressurized steam — filed under a genre the catalogue just calls Material Pop.
>
> The origin story going around: ISO-9000 started life as a factory noise-cancellation algorithm, before something changed after it was fed a decade of 90s J-Pop.
>
> We're not going to tell you whether that's true. That's the whole point of a label built around artists you can actually get lost in.
>
> Catalogue link in the comments. Come get lost.

**Suggested hashtags:** #AIMusic #MusicTech #Myndral #NewArtist
**Source:** `apps/corporate-website/src/content/generatedArtistCatalogue.ts` — ISO-9000's public bio and backstory, already live on the corporate site.

---

## Post 2 — NEW · Mystery / community-bait post · Plain text
**Format:** plain-text post designed for comments, not just likes · **Voice:** company/brand · **Goal:** turn an existing piece of lore into an active discussion
**Subject:** Sloane Valentine

### Full post
> Sloane Valentine doesn't do interviews. Doesn't do photos. Disgraced former child star, now making soundtracks for films that don't exist — that's the entire premise of The Valentine Syndicate's frontwoman.
>
> Here's the part we've never put in a press release: every one of her music videos contains exactly one frame from a film that was never released. One frame. Blink and you'll miss it.
>
> Some of our earliest listeners started screen-recording, slowing the footage down, and pulling that single frame out of each video — then lining them up in release order. The theory going around is that stitched together, they form one image. Somewhere in a desert. Something buried.
>
> We're not confirming or denying anything. We just make the music.
>
> If you've found a frame we haven't heard about yet, we'd genuinely like to know. Drop it below.

**Suggested hashtags:** #MusicTech #Myndral #EasterEgg #AIMusic
**Source:** `apps/corporate-website/src/content/generatedArtistCatalogue.ts` — Sloane Valentine's public bio and backstory, already live on the corporate site.

---

## Post 3 — Founder post · Plain text · Company Page *(unchanged)*
**Format:** plain-text post, no video · **Voice:** founder, first person plural · **Posts well from:** the Myndral company page or a founder's personal profile

### Full post
> Every few weeks someone asks me what Myndral actually is, expecting the answer to be "Spotify, but with AI music." It isn't, and that's on purpose.
>
> Spotify is a marketplace — millions of tracks, from anyone, ranked by algorithm. Myndral is a label. Every artist is created and maintained in-house. Every album is curated, not uploaded. Nothing gets in because a stranger clicked publish.
>
> Right now that's 24 artists and 40 albums, each with a real identity, a real backstory, and relationships to each other that carry across releases — a genuine musical universe, not a folder of generated tracks with album art slapped on. AI is part of how we make it, but it's not the pitch. Nobody falls in love with a generation pipeline. People fall in love with an artist whose story they can follow.
>
> We're not building a tool that makes music for you. We're building a label whose artists happen to not have been born — and holding ourselves to the same bar a real label would: coherence over volume, identity over novelty, a catalogue you can actually get attached to instead of scroll past.
>
> The app is about to go live. Premium is $4.49/month, and every dollar of it goes toward growing a universe we're not interested in flooding — only building right.

**Suggested hashtags:** #MusicTech #AIMusic #BuildInPublic #StartupLaunch
**Source:** `README.md`; `docs/decisions-log.md` 2026-05-19 (24/40 catalogue) and 2026-05-20 (pricing).

---

### Notes for Kartik
- Posts 1 and 2 deliberately never say the word "AI" or resolve the mystery — that matches how the real public bios are already written (`is_artificial_entity` is intentionally kept out of the public-facing copy), so the tone isn't new invention, just LinkedIn framing on canon that already exists.
- Post 2's comment-bait works better if there's actually something to point people toward — worth checking whether that "one hidden frame per video" detail is realized in the actual released video assets yet, or still just written lore. If it isn't live yet, hold this post until it is, or it reads as a promise the product can't cash.
- ISO-9000 and Sloane Valentine were picked because their backstories are the most visually/narratively striking of the roster — Naomi Sato (night-nurse-turned-lo-fi-artist) and The Weaver (Appalachian folk-horror recluse) are two more with the same hook potential if you want a rotating spotlight series out of this format.
