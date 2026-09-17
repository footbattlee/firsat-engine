# Creative flow

Current scope:

`deal_candidates -> canonical_products + cheapest offer + merchant -> real offers.image_url -> deterministic PNG`

The renderer deliberately does not publish anything. The next module will persist a publication queue and send the generated image to a Telegram admin bot for approve/reject actions. This keeps rendering, approval, and platform publishing independently retryable.
