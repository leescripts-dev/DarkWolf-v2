"""Leak-site inventory entries excluded from automated collection."""

from dataclasses import dataclass


@dataclass(frozen=True)
class TriageSite:
    name: str
    url: str
    reason: str


# These sites showed CAPTCHA, proof-of-work, or browser-verification pages.
# The collector records the classification and stops; it does not solve them.
CAPTCHA_LEAK_SITES = (
    TriageSite("BLACKLOCKS", "http://ybvjht7qcuhcml4pjcs7fgk57tzysplqtfq4i7yrwc6vjilin2dt2qad.onion/", "CAPTCHA marker in listing response"),
    TriageSite("Cloak", "http://cloak7jpvcb73rtx2ff7kaw2kholu7bdiivxpzbhlny4ybz75dpxckqd.onion/", "CAPTCHA verification page"),
    TriageSite("The Gentlemen", "http://tezwsse5czllksjb7cwp65rvnk4oobmzti2znn42i43bjdfd2prqqkad.onion/", "Gentlecloud browser-verification challenge"),
    TriageSite("Majinahanashi", "http://lthicpjqc7gkn5eq3epxndc2uig3yngvcbdya4u3m3byjod5km4yuwqd.onion/#blog", "Slider/pattern verification challenge"),
    TriageSite("Handala Hack Team", "https://handala-hack.tw/", "Bot-verification interstitial; the supplied flow requires a human verification checkbox"),
)


# Reached a page without CAPTCHA, but the listing extractor returned no
# victim records. Entries are populated after a verified scrape, not merely
# from a failed network request or a static loading shell.
MANUAL_INSPECTION_LEAK_SITES = (
    TriageSite("DarkBit Ransomware", "https://t.me/DarkBitChannel", "Reachable Telegram landing page; no victim listing exposed"),
)


# The source did not respond through the configured Tor service during the
# latest probe. This is kept separate from manual inspection and CAPTCHA.
UNAVAILABLE_LEAK_SITES = (
    TriageSite("0day Syndicate", "http://odaygplp3zhyx7zl45egetl6dzc4reduisnoyym34rjdmaryfaz5doqd.onion", "No response through the configured Tor service during first-page inspection"),
    TriageSite("BravoX", "http://bravoxxtrmqeeevhl7gdh2yzvlrjxajr66d33c7ozosrccx4cz7cepad.onion", "No response through the configured Tor service during first-page inspection"),
    TriageSite("Coinbase Cartel", "http://fjg4zi4opkxkvdz7mvwp7h6goe4tcby3hhkrz43pht4j3vakhy75znyd.onion/", "No response through the configured Tor service during first-page inspection"),
    TriageSite("Embargo", "http://embargobe3n5okxyzqphpmk3moinoap2snz5k6765mvtkk7hhi544jid.onion/#/", "No response through the configured Tor service during first-page inspection"),
    TriageSite("Kyber Ransomware", "http://kyblogtz6k3jtxnjjvluee5ec4g3zcnvyvbgsnq5thumphmqidkt7xid.onion/", "No response through the configured Tor service during first-page inspection"),
    TriageSite("Helix", "http://helixr2sncrd3ndsz5oho6mzqw3x5u7mvox5zcsngc5wm7v4l5k7oryd.onion/leaks/", "The supplied /leaks/ route and root timed out through the configured Tor service on 2026-10-19"),
    TriageSite("Meowciety403", "http://hqhx32msbc545v233d55cvjedj5rqnv55bvzkavjv2q46qwuuannc4id.onion/", "No response through the configured Tor service during first-page inspection"),
    TriageSite("MyData Ransomware", "http://mydatae2d63il5oaxxangwnid5loq2qmtsol2ozr6vtb7yfm5ypzo6id.onion/blog", "No response through the configured Tor service during first-page inspection"),
    TriageSite("NightSpire", "http://nspirebcv4sy3yydtaercuut34hwc4fsxqqv4b4ye4xmo6qp3vxhulqd.onion/database", "No response through the configured Tor service during first-page inspection"),
    TriageSite("Nova", "http://novadmrkp4vbk2padk5t6pbxolndceuc7hrcq4mjaoyed6nxsqiuzyyd.onion", "No response through the configured Tor service during first-page inspection"),
    TriageSite("Orion Leaks", "http://cjfntkj5qeizxowuy3srceg7zo6namc3kfeor7pfn6bpdkl3w265ooid.onion/news/home", "No response through the configured Tor service during first-page inspection"),
    TriageSite("Payouts King", "http://payoutsgn7cy6uliwevdqspncjpfxpmzgirwl2au65la7rfs5x3qnbqd.onion/", "No response through the configured Tor service during first-page inspection"),
    TriageSite("Reynolds", "http://bs2tlg32pfjwmclm22cyngqmoo24cdlhfxzbruwrdaxumisfeory32qd.onion/", "No response through the configured Tor service during first-page inspection"),
    TriageSite("Section9", "http://v76bdil3v7hczufr7kwk75eq6oks27d3qwj6v5ajj6v6rubbvwhcq2qd.onion/", "No response through the configured Tor service during first-page inspection"),
    TriageSite("Stormous", "http://pdcizqzjitsgfcgqeyhuee5u6uki6zy5slzioinlhx6xjnsw25irdgqd.onion/", "No response through the configured Tor service during first-page inspection"),
    TriageSite("ThreeAM", "http://threeamkelxicjsaf2czjyz2lc4q3ngqkxhhlexyfcp2o6raw4rphyad.onion/", "No response through the configured Tor service during first-page inspection"),
    TriageSite("TiMc", "http://rzzfiwoop67jrxadngcy7nvjm7suwtrjznview63ooowqfsm5sq7gmqd.onion", "No response through the configured Tor service during first-page inspection"),
    TriageSite("TridentLocker", "http://tridentfrdy6jydwywfx4vx422vnto7pktao2gyx2qdcwjanogq454ad.onion/articles", "No response through the configured Tor service during first-page inspection"),
    TriageSite("Triple X", "http://ojcmpbdncjo5dhaxxll44bq6to3kwqtoeraevgsjquhdtt4uv5l4igid.onion", "No response through the configured Tor service during first-page inspection"),
    TriageSite("UMBRA", "http://umbra7isogjsgdcndz3uu6qvl5zftjptt6s3iiuecjlwbt4yqyvrhcid.onion/", "No response through the configured Tor service during first-page inspection"),
    TriageSite("Underground", "http://47glxkuxyayqrvugfumgsblrdagvrah7gttfscgzn56eyss5wg3uvmqd.onion/", "No response through the configured Tor service during first-page inspection"),
    TriageSite("CRPx0", "http://tlxoddx4odmc2qvsmtsbgwwsv5j45osb5sox7mz6izxliuju5mkulzad.onion/index.php", "No response through the configured Tor service during the 2026-10-13 recheck"),
    TriageSite("DYSPHOR1A", "http://y3maveiwszbnrziufbbberx74cvrdcsf72nxzuqxzv7ppdmmqzffazid.onion/", "No response through the configured Tor service during the 2026-10-13 recheck"),
    TriageSite("ExfilSquad", "http://exfil5gqmbxrg6yky5aeitkdj7kfwxxjh3wxzrtlewjqi2x67o634iyd.onion", "No response through the configured Tor service during the 2026-10-13 recheck"),
    TriageSite("EXFS Team", "http://y7pigjllv5mqgxh6jgvdim74f5hvanzrgvkpzdfvfsetewryky7xoqyd.onion/", "No response through the configured Tor service during the 2026-10-13 recheck"),
    TriageSite("Medusa", "http://medusaxko7jxtrojdkxo66j7ck4q5tgktf7uqsqyfry4ebnxlcbkccyd.onion/", "No response through the configured Tor service during the 2026-10-13 recheck"),
    TriageSite("Meow", "http://meow6xanhzfci2gbkn3lmbqq7xjjufskkdfocqdngt3ltvzgqpsg5mid.onion/", "No response through the configured Tor service during the 2026-10-13 recheck"),
    TriageSite("NightSpire (mirror 2)", "http://a2lyiiaq4n74tlgz4fk3ft4akolapfrzk772dk24iq32cznjsmzpanqd.onion/datas.php", "No response through the configured Tor service during the 2026-10-13 recheck"),
    TriageSite("NightSpire (mirror 3)", "http://nspirep7orjq73k2x2fwh2mxgh74vm2now6cdbnnxjk2f5wn34bmdxad.onion/database", "No response through the configured Tor service during the 2026-10-13 recheck"),
    TriageSite("Prinz Eugen", "http://prinzkpn6d3itrgcytmsmlcpt5mgwn3ihpck2hsed5cezlbtbi3wklid.onion/campaigns", "No response through the configured Tor service during the 2026-10-13 recheck"),
    TriageSite("ShinyHunters", "http://espeonsh2drryv4bsonur5ud7d6gooho2mvktqdmakdpoxkwwersinid.onion", "No response through the configured Tor service during the 2026-10-13 recheck"),
    TriageSite("Space Bears", "http://5butbkrljkaorg5maepuca25oma7eiwo6a2rlhvkblb4v6mf3ki2ovid.onion/", "No response through the configured Tor service during the 2026-10-13 recheck"),
    TriageSite("SPIRALS", "http://spiralstfe7rtbna7zlv6szdwmjvjszf2d64zkf6z5jykrwnw5jbgpyd.onion", "No response through the configured Tor service during the 2026-10-13 recheck"),
    TriageSite("Warlock", "http://warlockhga5iw3t54ps5iytlilf7hlvxy7kwrkidspn4qoh64s4vsuyd.onion", "No response through the configured Tor service during the 2026-10-13 recheck"),
    TriageSite("World Leaks", "http://worldleaksartrjm3c6vasllvgacbi5u3mgzkluehrzhk2jz4taufuid.onion", "No response through the configured Tor service during the 2026-10-13 recheck"),
    TriageSite("xpl0itrs", "http://2kieaq6jnwgrru62wwtxaafg35q6rzweg7y2xjfnbhvq5wd4eojqv6yd.onion", "No response through the configured Tor service during the 2026-10-13 recheck"),
    TriageSite("ZaWoo", "https://fyenuhkq3pfhnbpidj5jm2fl2lryxip4byhg6eozynrnlomu4szf2nyd.onion/", "No response through the configured Tor service during the 2026-10-13 recheck"),
)
