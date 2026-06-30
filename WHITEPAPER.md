# How We Rank Local Businesses

### A plain-language guide to the Best of Life ranking methodology

**Version 1.0 — June 2026**

---

## Abstract

Most "best of" lists are popularity contests. They reward whoever has the most
followers, the biggest ad budget, or the most aggressive review-collection tactics —
not necessarily the businesses that treat their customers best. We set out to build
something different: a ranking that measures **how good a business actually is at
serving its community**, drawing on every piece of publicly available evidence and
combining it in a way that is transparent, fair to small businesses, and hard to game.

This paper explains, without assuming any technical background, how that ranking
works. We describe the six dimensions we measure, why we weight customer satisfaction
and service above digital polish, how we keep a single glowing review from outranking
a thousand genuine ones, and why we compare every business only against its true
neighbours rather than against the whole city. Our goal is for any business owner,
diner, or curious reader to finish this paper understanding exactly why a business
landed where it did.

---

## 1. The problem with most rankings

If you have ever searched for "best coffee near me," you have seen the usual suspects:
the place with a four-and-a-half-star average and ten thousand reviews sits at the top,
and a tiny café with a perfect five-star average and forty reviews is buried on page
three. Both of those signals are misleading in opposite directions.

A business with a huge number of reviews is not automatically better — it might simply
be older, bigger, or in a busier location. And a business with a perfect average is not
automatically better either — a handful of reviews from friends and family can produce a
flawless score that says nothing about how the business treats a stranger on a Tuesday
night.

Worse, almost every ranking you encounter measures only **one thing**: a star rating.
That single number cannot tell you whether the staff were kind, whether the place was
clean, whether you waited an hour, or whether the price matched the experience. It also
quietly favours businesses that have learned to *farm* reviews over those that simply do
good work and let word of mouth do the rest.

We wanted a ranking that reflects the question a real person actually asks: **"If I walk
in here, am I going to have a good experience?"** Answering that honestly requires
looking at many kinds of evidence at once, weighing them thoughtfully, and being
explicit about how the final number is built.

---

## 2. Our guiding principles

Before describing the mechanics, it helps to state the values that shaped every
decision.

**Service and satisfaction come first.** A clean, easy-to-use website is a nice signal —
it often means a business is organized and customer-focused. But it is not what makes a
restaurant great. So digital presence is *one* ingredient in our ranking, never the main
course. The largest share of a business's score comes from how satisfied its customers
are and how well it serves them.

**Small businesses deserve a fair shot.** A neighbourhood gem with a few hundred genuine
reviews should be able to outrank a chain with a marketing department. Our method
deliberately avoids letting raw size or raw popularity dominate.

**Compare like with like.** A bakery in Kensington Market should be judged against other
Kensington Market bakeries, not against a steakhouse in Yorkville. Every ranking we
produce is *local* and *category-specific*.

**Be hard to game.** Any signal that can be bought or faked — a burst of five-star
reviews, a flood of backlinks — is treated with suspicion and balanced against signals
that are much harder to manufacture, like the consistency of sentiment across years of
written reviews and across independent platforms.

**Be explainable.** For every business, we can show exactly which dimensions lifted it up
or held it back. There is no secret sauce, only a published recipe.

---

## 3. The six dimensions we measure

Rather than collapse a business into a single star rating, we evaluate it across six
distinct dimensions, which we call **pillars**. Each pillar is scored from 0 to 100, and
each captures something a star rating alone cannot.

**1. Customer Satisfaction (the largest share).** How happy are customers, really? We
take the average ratings a business has earned across multiple independent platforms,
adjust them for trustworthiness (explained in Section 4), and reward businesses whose
reputation is *consistent* across those platforms. A business that is loved equally on
two different review sites is more credibly good than one that looks great on a single
site it may have cultivated.

**2. Service Quality.** This is where we go beyond the star and read what people
actually wrote. Using language analysis, we measure the sentiment in reviews
specifically around service and staff, waiting times, cleanliness, and value for money.
We also track how often reviews contain genuine complaints. A business can have a decent
average rating and still have a service problem hiding in its written reviews — this
pillar surfaces it.

**3. Popularity and Reputation.** Here we acknowledge that *how many* people have an
opinion matters — but carefully. We measure the total volume of reviews across
platforms, whether the business shows up on more than one platform at all, and how often
it is mentioned organically in community discussions (for example, locals recommending
it on Reddit). Crucially, this pillar is weighted modestly, so popularity supports a
strong ranking but never single-handedly creates one.

**4. Digital Presence.** Does the business have a working, modern, usable website? We
check practical, customer-facing things: whether the site is secure, works on a phone,
loads real content, and is structured so search engines and AI assistants can
understand it. A good digital channel makes a business easier to find and trust. A
business with no website is not disqualified — but a business that has invested in a
clean one earns a modest, well-deserved bump.

**5. Search Visibility.** When someone searches for this kind of business, can they find
this one? We measure the business's organic search footprint and where it appears in
search results for the relevant query. This rewards businesses that have earned genuine
discoverability rather than those that have merely bought ads.

**6. AI Visibility.** Increasingly, people ask an AI assistant "what's the best X in this
neighbourhood?" We test exactly that: we ask leading AI models the question and record
whether they recommend the business. This is a forward-looking signal for how
discoverable a business is in the way people are starting to search.

---

## 4. Keeping the score honest

Two technical ideas do most of the work of keeping our ranking fair. Both can be
explained without mathematics, though we include the simple formulas for the curious.

### 4.1 Not all averages are equal: trust grows with evidence

Imagine two cafés. One has a single five-star review. The other has eight hundred
reviews averaging 4.6 stars. A naive ranking would put the first café ahead — a perfect
5.0 beats a 4.6. But common sense says the opposite: one review tells us almost nothing,
while eight hundred reviews tell us a great deal.

We solve this with a long-established statistical technique often described as
**"shrinking toward the average."** Every business's rating is gently pulled toward a
neutral baseline, and the fewer reviews it has, the harder it is pulled. A business with
thousands of reviews barely moves — its rating is well-earned. A business with only one
or two reviews is pulled most of the way back to neutral, because we simply do not yet
have enough evidence to trust its perfect score.

> In practice, an adjusted rating is computed as:
>
> ```
> adjusted = (C × m  +  n × r) / (C + n)
> ```
>
> where `r` is the business's raw average, `n` is its number of reviews, `m` is the
> neutral baseline (we use 4.0), and `C` is the "strength" of that baseline (we use 20,
> roughly meaning a business needs more than ~20 reviews before its own average starts to
> dominate). The single five-star review above becomes about 4.05; the 4.6 with eight
> hundred reviews stays at about 4.59 and wins easily.

This one idea quietly protects the entire ranking from being hijacked by a small number
of glowing — or hostile — reviews.

### 4.2 Fair comparisons: every business is judged against its true neighbours

A score of "72 out of 100" means nothing in isolation. Seventy-two compared to what?

So after we compute each pillar, we do not use the raw numbers directly. Instead, within
each topic — for example, *Best Brunch in Leslieville* — we rank every competing
business against the others on that pillar and convert the result into a percentile. A
business in the 90th percentile for service simply did better on service than 90% of its
direct competitors in that neighbourhood.

This **within-topic normalization** has two important effects. First, it makes
comparisons fair: a strong field and a weak field are each judged on their own terms.
Second, it means a business is never penalized for the city as a whole — only for how it
stacks up against the places a customer would realistically choose between.

If a business is missing one signal entirely — say, it has no website, so it has no
search data — we do not punish it as though it scored zero. We treat the missing pillar
as neutral and let the dimensions we *can* measure speak, then re-balance the weights
across the pillars that are present. A business is judged on the evidence it has, not
penalized for evidence that does not exist.

---

## 5. Putting it together: the final score

Once each business has six normalized pillar scores, we combine them into a single
final score using a weighted average. The weights reflect our principles — customer
satisfaction carries the most influence, service quality is next, and the more
gameable or secondary signals carry less:

| Pillar | What it captures | Weight |
|---|---|---|
| Customer Satisfaction | Trust-adjusted ratings across platforms, consistency | 30% |
| Service Quality | What written reviews say about service, waits, cleanliness, value | 20% |
| Popularity / Reputation | Review volume, cross-platform presence, community mentions | 15% |
| Digital Presence | A secure, modern, usable website | 15% |
| Search Visibility | Organic discoverability for the relevant search | 10% |
| AI Visibility | Whether AI assistants recommend the business | 10% |

The result is a number from 0 to 100, and a rank position within the topic. When two
businesses score nearly identically, we break the tie in favour of the one with stronger
customer satisfaction, and then greater review volume — again keeping the emphasis where
our principles say it belongs.

These weights are not buried in code. They live in a single configuration file and can
be reviewed, debated, and adjusted openly. If the community decides service should count
for more, that is a one-line change with a clear, documented effect.

---

## 6. Where the evidence comes from

A ranking is only as good as the evidence behind it. We deliberately draw on **many
independent sources** so that no single platform — and no single tactic for manipulating
that platform — can determine an outcome. For each business we gather, where available:

- **Mapping and review platforms** (such as Google and Yelp) for ratings, review
  counts, and the full text of reviews.
- **The business's own website**, which we examine for security, mobile-friendliness,
  and content quality.
- **Search-engine data** showing the business's organic visibility.
- **Community discussion** where locals organically mention and recommend places.
- **AI assistants**, which we query directly to see whom they recommend.

All of this is **publicly available information** — the same evidence any diligent person
could gather by hand, simply assembled at scale and weighed consistently.

We refresh this evidence and recompute every ranking **once a month**. Local businesses
change: a new chef arrives, service slips, a renovation lands. A monthly cadence keeps
the rankings current without overreacting to a single bad week.

---

## 7. Why this is hard to game

No ranking is perfectly immune to manipulation, but ours is designed to make
manipulation expensive and ineffective:

- **Buying a burst of five-star reviews** has limited effect, because trust-adjusted
  ratings discount small or sudden review volumes, and because satisfaction is only one
  of six pillars.
- **Faking consistency is hard.** Looking good on a single platform is achievable;
  looking equally good across multiple independent platforms, *and* in the written
  sentiment of reviews, *and* in unprompted community mentions, is much harder to
  fabricate.
- **Buying search backlinks** influences only a small, capped portion of one pillar.
- **Marketing spend doesn't move the needle directly** — we measure *organic*
  visibility, not advertising.

To climb our ranking, the cheapest strategy is also the most honest one: serve customers
well, consistently, over time. That is exactly the behaviour the ranking exists to
reward.

---

## 8. Honest limitations

We believe in being candid about what our method cannot do.

**It reflects what people write down.** Businesses whose customers rarely leave reviews —
common in some communities and some categories — will have thinner evidence. We mitigate
this by drawing on multiple sources and by treating missing evidence as neutral rather
than negative, but a quiet, excellent business can still be underrepresented.

**Language analysis is imperfect.** Automated reading of reviews captures sentiment well
in aggregate but can miss sarcasm or cultural nuance in any single review. Because we
work across many reviews, individual errors tend to wash out, but they are real.

**Newer and very small businesses carry uncertainty.** With little history, our
confidence in their score is genuinely lower — which is the honest position, even if it
is sometimes frustrating for a promising newcomer.

**We measure the measurable.** Some of what makes a place special — a particular warmth,
a neighbourhood history — resists quantification. Our ranking is a strong, evidence-based
guide, not a substitute for personal taste.

We publish these limitations because a ranking that hides its weaknesses cannot ask for
the public's trust.

---

## 9. Transparency and governance

Three commitments make this methodology accountable:

1. **The recipe is public.** The pillars, the weights, and the logic in this paper are
   the actual logic the system uses. There is no hidden override.
2. **Every result is explainable.** For any business, we can show its six pillar scores
   and how each contributed to its final position.
3. **The method can evolve in the open.** Weights and definitions live in plain
   configuration, and changes are documented so anyone can see what changed and why.

A business that wants to rank higher does not need to guess. The path is written down,
and it is the same path that produces genuinely better experiences for customers.

---

## 10. Conclusion

We built this ranking because the people who run great local businesses — the careful
baker, the patient mechanic, the family-run restaurant that has fed a neighbourhood for
twenty years — deserve to be found, and the people looking for them deserve an honest
guide.

By measuring six dimensions instead of one, by trusting evidence in proportion to its
weight, by comparing every business only against its real neighbours, and by putting
customer satisfaction and service ahead of digital polish, we have tried to build a
ranking that rewards the thing that actually matters: treating people well. The method
is not perfect, and we have said where it falls short. But it is fair, it is
transparent, and it is hard to fake — and for a public "best of" list, those three
properties are worth more than any single clever number.

---

*This document describes the ranking methodology behind Best of Life. The pillars,
weights, and statistical methods described here correspond directly to the published,
configurable logic of the ranking pipeline. For the technical implementation, see the
accompanying project documentation.*
