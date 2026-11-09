from dataclasses import dataclass


@dataclass(frozen=True)
class JavascriptLeakSite:
    slug: str
    name: str
    url: str
    item_selector: str | None = None
    name_selector: str = "h1,h2,h3,h4,[class*='title']"
    country_selector: str = "[class*='country'],[class*='location']"
    date_selector: str = "time,[class*='date']"
    alternate_urls: tuple[str, ...] = ()
    api_url: str | None = None


# Sites classified as JavaScript driven in the recon
# inventory. INC is already covered by its dedicated collector; OROVA and
# SHIBA use the API collector.
JAVASCRIPT_LEAK_SITES = (
    JavascriptLeakSite("everest", "Everest", "http://everestndkvzcibcje2cqxhre2hmmybl3rn2gwzwsblz7gx6uryn5rad.onion/"),
    JavascriptLeakSite("exitium", "Exitium", "http://m3ksukzn2glzfdvlusohril7n3iyk4z4fudf6mm22lwhpbpt5aiee5qd.onion/", ".target-card", ".card-name"),
    JavascriptLeakSite("atomsilo", "Atomsilo", "http://npmh5ahrgakbniuntyc7io4adm6ietbdbuejrfonowqtyqn24or556qd.onion/leaks.html", ".leak-card", ".leak-title"),
    JavascriptLeakSite("abyss", "Abyss", "http://3ev4metjirohtdpshsqlkrqcmxq6zu3d7obrdhglpy5jpbr7whmlfgqd.onion/", ".card", ".card-title"),
    JavascriptLeakSite("ailock", "AiLock", "http://dhnsppqjaaa22lsqxl2tfhji4ca43743kubltnodvsft3hkvai77p6ad.onion/", "[class*='news']", "h3"),
    JavascriptLeakSite("black_nevas", "Black Nevas", "http://ctyfftrjgtwdjzlgqh4avbd35sqrs6tde4oyam2ufbjch6oqpqtkdtid.onion/", "[class*='publication'],[class*='victim'],[class*='card']"),
    JavascriptLeakSite("cry0", "cry0", "http://cryoblogedawivdcknyd4jsjxkrx3xrqqltxla6wwjjnzm3f3jaxjzqd.onion/", "article"),
    JavascriptLeakSite("dark_project", "Dark Project", "http://darkprn3d3udnhpuxknsrhft3376lrz5tenhgkrxge5hxqe46pkbrwid.onion/", "[class*='company'],[class*='victim'],[class*='target'],article", "h2,h3,h4,[class*='title']"),
    JavascriptLeakSite("play_ransomware", "Play ransomware", "http://j75o7xvvsm4lpsjhkjvb4wl2q6ajegvabe6oswthuaubbykk4xkzgpid.onion/index.php", "th.News", "th.News", alternate_urls=("http://ipi4tiumgzjsym6pyuzrfqrtwskokxokqannmd6sa24shvr7x5kxdvqd.onion/index.php",)),
    JavascriptLeakSite("eclipse", "Eclipse", "http://eclipse4g5kxfwsvpu4qx5sdcnrji6gxl5gt67bucjlgt35g7akvjoid.onion/", "article,[class*='card'],[class*='victim']"),
    JavascriptLeakSite("gammax", "GAMMAX", "http://gammax6w3dkfdjfrjthtmqzsioue52vzy6lz54qy6jcvmogfpubutjyd.onion/", "article.post-card", "h2.post-title"),
    JavascriptLeakSite("kairos", "Kairos", "http://kairosgeuzkzz3ajntqcyxl3ib36szz3mg62mb3zbui33pbk3uzo4qqd.onion/catalog", "[class*='company'],[class*='victim'],[class*='card']", "h2,h3,h4,[class*='title']"),
    JavascriptLeakSite("leaknet", "Leaknet", "http://nleakk6sejx45jxtk7x6iyt65hwvfrkifc5v7ertdlwm3gttbpvlvxqd.onion", "article,[class*='post'],[class*='card']"),
    JavascriptLeakSite("lynx", "Lynx Ransomware", "http://lynxblogxstgzsarfyk2pvhdv45igghb4zmthnzmsipzeoduruz3xwqd.onion/leaks", "table tbody tr,[class*='company'],[class*='victim']", "td:first-child,h2,h3,h4,[class*='title']"),
    JavascriptLeakSite("money_message", "Money Message", "http://blogvl7tjyjvsfthobttze52w36wwiz34hrfcmorgvdzb6hikucb7aqd.onion/", "article,[class*='post'],[class*='card']"),
    JavascriptLeakSite("morpheus", "Morpheus", "http://izsp6ipui4ctgxfugbgtu65kzefrucltyfpbxplmfybl5swiadpljmyd.onion/", "article,[class*='feed'],[class*='post'],[class*='card']"),
    JavascriptLeakSite("panzer", "Panzer", "http://pnzruro7syvwvefx5mpo2fhzi4jftgquynsqf3vy5x3no57yp2iz4nyd.onion/", "article,[class*='victim'],[class*='company'],[class*='card']"),
    JavascriptLeakSite("global", "Global", "http://globaldonejcrwbe7ujwuzptsummx3rvba54wcjoxrjvqgo37y4aqwid.onion/", "[class*='target'],[class*='victim'],[class*='company'],[class*='card']", "h2,h3,h4,[class*='title']"),
    JavascriptLeakSite("sovcali", "Sovcali", "http://z3mojpjnxt5tgqvu4wgosihl7pxvrcbyjcgquw2bwkyye5gwbhnf4kqd.onion/index.html", "article,.post,[class*='entry']", "h2,h3,h4,[class*='title']"),
    JavascriptLeakSite("termite_ransomware", "Termite Ransomware", "http://termiteuslbumdge2zmfmfcsrvmvsfe4gvyudc5j6cdnisnhtftvokid.onion/", api_url="http://35lnaldrbugg5zz7ju5wjsil45aqglx2ckvsgijj533stmtrvgi3nmad.onion/api/blog/blogs"),
    JavascriptLeakSite("titan", "TITAN", "http://x4bccxlsmjsxlnnf3ocvndlshgfkagzytpqmsjnlfykceumnw6i4hkqd.onion/leaked", "h2"),
    JavascriptLeakSite("lockbit", "LockBit", "http://lockbitapt67g6rwzjbcxnww5efpg4qok6vpfeth7wx3okj52ks4wtad.onion/", ".post-block", ".post-title", date_selector=".updated-post-date"),
    JavascriptLeakSite("ulose", "ULOSE", "http://egm34gsyx65wb6jyqds4esvkskl34barx4robuebjhqpc4dfeavg7fyd.onion/", "article,[class*='victim'],[class*='company'],[class*='card']"),
    JavascriptLeakSite("blackx", "BlackX", "http://blackxppq2jvqyg4slyg3sbszv7ib2avaaycvhff5qipgdoepqi57xyd.onion/", api_url="http://blackxppq2jvqyg4slyg3sbszv7ib2avaaycvhff5qipgdoepqi57xyd.onion/api/targets"),
    JavascriptLeakSite("insomnia", "Insomnia", "http://i62huw7ve22rpyw6lnq3kmfump2dmsg4xpveec3ere73njwatrz74gad.onion/", ".book-card", ".info-title a", ".card-meta", ".card-meta"),
    JavascriptLeakSite(
        "storm",
        "Storm",
        "http://yqhecvqtdvq6p7duqcgw2qca77spbgakxcoibtx6zpvfshltsbbbhfqd.onion/",
        "article,[class*='victim'],[class*='company'],[class*='target'],[class*='card']",
        "h1,h2,h3,h4,[class*='title'],[class*='name']",
        "[class*='country'],[class*='location']",
        "time,[datetime],[class*='date'],[class*='posted']",
        api_url="http://yqhecvqtdvq6p7duqcgw2qca77spbgakxcoibtx6zpvfshltsbbbhfqd.onion/api-2b6e6040d4a1c5a1/companies",
    ),
    JavascriptLeakSite(
        "settra",
        "Settra",
        "http://settra5ldqwgtw5q7z5awbsvlksakyfojuc5slgrz5lvapune4fantqd.onion/",
        "a[href^='/leaks/']",
        "h3",
        date_selector="time,[class*='date']",
    ),
)

