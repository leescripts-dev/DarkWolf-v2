from dataclasses import dataclass


@dataclass(frozen=True)
class HtmlLeakSite:
    slug: str
    name: str
    url: str


# Active HTML listing collectors. Sources that are protected or yield no
# records are kept separately in triage_registry.py.
HTML_LEAK_SITES = (
    HtmlLeakSite("genesis", "Genesis", "http://genesis6ixpb5mcy4kudybtw5op2wqlrkocfogbnenz3c647ibqixiad.onion/"),
    HtmlLeakSite("brain_cipher", "Brain Cipher", "http://vkvsgl7lhipjirmz6j5ubp3w3bwvxgcdbpi3fsbqngfynetqtw4w5hyd.onion/"),
    HtmlLeakSite("deadlock_ransomware", "DeadLock Ransomware", "http://deadblogdbdu5wprek7wa2o4ce7rnt6u6ntqeud3hzjjcveosgpsqqqd.onion/"),
    HtmlLeakSite("dire_wolf", "Dire Wolf", "http://direwolfcdkv5whaz2spehizdg22jsuf5aeje4asmetpbt6ri4jnd4qd.onion/"),
    HtmlLeakSite("imnotavillain", "ImNotAVillain", "http://o6rtgcjdjqyimjxexpejddhdfbehsjn4fcsazfkgwydeb27gqhtdntyd.onion/leaks.html"),
    HtmlLeakSite("interlock", "INTERLOCK", "http://ebhmkoohccl45qesdbvrjqtyro2hmhkmh6vkyfyjjzfllm3ix72aqaid.onion/leaks.php"),
    HtmlLeakSite("krybit", "Krybit", "http://krybitxdpxohsmjooeb3gbgpmdddreh6mnflzac6bnezz74b7yje67yd.onion/"),
    HtmlLeakSite("netrunner_pr", "NetRunner PR", "http://netrunnlekx5rsfc7l3k3wbczr5m7rbdlgmf6aeyvgo5rsakki6ljjqd.onion/"),
    HtmlLeakSite("notrace_group", "NoTrace Group", "https://notrace.ar.io/"),
    HtmlLeakSite("apt73_bashe", "APT73 (BASHE)", "http://basheqtvzqwz4vp6ks5lm2ocq7i6tozqgf6vjcasj4ezmsy4bkpshhyd.onion/"),
    HtmlLeakSite("arcus_media", "ARCUS MEDIA", "http://arcuufpr5xxbbkin4mlidt7itmr6znlppk63jbtkeguuhszmc5g7qdyd.onion/"),
    HtmlLeakSite("barracuda", "BARRACUDA", "http://uvm6hk4wwstfddja5z5htgtlehmfyflffijz6iozsuqyacyibzxefkqd.onion/leaks"),
    HtmlLeakSite("blackwater", "BLACKWATER", "http://ejzl7cjxmkx7lzhiqwidmrwtfjv45pkczbc4fnyaut3t7gll3yaiq5id.onion/"),
    HtmlLeakSite("cinder", "Cinder", "http://iah6477wcvisc45wl54u524fbrh4dnmtcctpg2fpe5epf3jbpkiwu4qd.onion/"),
    HtmlLeakSite("cmd_organization", "CMD organization", "http://cmdnkiqjije2tllr3biee2sjgj3i4robg2cbtilbnytdhh2wy3syrlyd.onion/"),
    HtmlLeakSite("daixin_ransomware", "Daixin Ransomware", "http://7ukmkdtyxdkdivtjad57klqnd3kdsmq6tp45rrsxqnu76zzv3jvitlqd.onion/"),
    HtmlLeakSite("doommageddon", "DOOMMAGEDDON", "http://iacjvmxjb2ivqkxxzmde4w6g53gn6ym7c3g6mfifvejyhqtp4wrkypyd.onion/"),
    HtmlLeakSite("emperador", "Emperador", "http://emprdr4p7iwlhpky33tswt3k2qdeljyjcdpoysabudmmrz4z32laexad.onion/"),
    HtmlLeakSite("endzone", "ENDZONE", "http://endzonezgz3sqzmtqg4acp4z7ao7xc6vunfhezjsnfqrm2ksudsredyd.onion/"),
    HtmlLeakSite("falcon", "Falcon", "http://i7loab6thvz4lb7jdr3qoeumbvilwhbgnwsctnlfmvsv7g5s3vsiw6yd.onion/companies"),
    HtmlLeakSite("global_secret_group", "Global Secret Group", "http://o5lsqyar7ox25z734k6zaxt2vf7bsyi4q5rturi5iyxzqo3ica7bjsad.onion/"),
    HtmlLeakSite("karma_leaks", "Karma Leaks", "http://2dmzkuruwpmgalhcn26kmvlg37ijqbzqo3orhxwvyf2nf3w4gfq6ikid.onion/leaks"),
    HtmlLeakSite("qilin", "Qilin", "http://ijzn3sicrcy7guixkzjkib4ukbiilwc3xhnmby4mcbccnsd7j2rekvqd.onion/"),
    HtmlLeakSite("kazu", "Kazu", "http://6czlbd2jfiy6765fbnbnzuwuqocg57ebvp3tbm35kib425k4qnmiiiqd.onion/ransom.html"),
    HtmlLeakSite("ms13_089_blog", "MS13-089 Blog", "http://msleakjir7pxbe6onlqe5uwgvdmy6nq4mnwfy7ojswbhnleenm77vgad.onion/"),
    HtmlLeakSite("secp0", "SECP0", "http://secponewsxgrlnirowclps2kllzaotaf5w2bsvktdnz4qhjr2jnwvvyd.onion/"),
    HtmlLeakSite("vexy", "Vexy", "http://vexytsr3chimdz6siwaqi2lvxxwfkxvffkpwyanr2llequ2hkm56jvqd.onion/blog"),
    HtmlLeakSite("unsafe", "UnSafe", "http://unsafeipw6wbkzzmj7yqp7bz6j7ivzynggmwxsm6u2wwfmfqrxqrrhyd.onion/"),
    HtmlLeakSite("non", "N0n", "http://nongzecboljwv3yfndkggsybsglfrkffw7bvk2zemuteoxe6etpusnad.onion/"),
    HtmlLeakSite("payload", "Payload", "http://payloadrz5yw227brtbvdqpnlhq3rdcdekdnn3rgucbcdeawq2v6vuyd.onion/"),
    HtmlLeakSite("rhysida", "Rhysida", "http://rhysidafc6lm7qa2mkiukbezh7zuth3i4wof4mh2audkymscjm6yegad.onion/"),
    HtmlLeakSite("redact", "REDACT", "http://neclc36yt4yaa5lv54kh4qbhvjcvuv6nnaurqowkellytpvj3afh4aid.onion/companies"),
    HtmlLeakSite("safepay", "SafePay", "http://safepaypfxntwixwjrlcscft433ggemlhgkkdupi2ynhtcmvdgubmoyd.onion/"),
    HtmlLeakSite("audit_team", "SECURITY AUDIT (Audit Team)", "http://6tdqqaxftvradka5d2frzgwixis7fmro7rfh4ettzcx7jfapkebe6jad.onion/"),
    HtmlLeakSite("arachna", "Arachna Leaks", "http://ptyctpveqfevlukjw4hpdh6nb5oiemq6ek6tuuvxbtrfghvuutvscsid.onion/"),
    HtmlLeakSite("beast_leaks", "Beast Leaks", "http://beast6azu4f7fxjakiayhnssybibsgjnmy77a6duufqw5afjzfjhzuqd.onion/"),
    HtmlLeakSite("blackout_ransomware", "Blackout Ransomware", "http://black3gnkizshuynieigw6ejgpblb53mpasftzd6pydqpmq2vn2xf6yd.onion/"),
    HtmlLeakSite("clop", "Clop", "https://clopofffr7tth6hsvxx3cys4qkshrbbiitnxfwts6hj64mtnaovjieyd.onion/"),
    HtmlLeakSite("fulcrum_sec", "Fulcrum Sec", "http://4e3p3in2bl67hxchuwza7qvnpe7pyeloyztr5fnh257fxkovfhappjyd.onion/"),
    HtmlLeakSite("toufan_leaks", "Toufan Leaks", "https://toufanleaks.org/"),
    HtmlLeakSite("leakeddata", "LeakedData", "http://business-data-leaks.com/about/"),
    HtmlLeakSite("ransomexx_v2", "RansomEXX v2", "http://rnsm777cdsjrsdlbs4v5qoeppu3px6sb2igmh53jzrx7ipcrbjz5b2ad.onion/"),
    HtmlLeakSite("run_some_wares", "Run Some Wares", "http://rnsmwareartse3m4hjsumjf222pnka6gad26cqxqmbjvevhbnym5p6ad.onion/"),
    HtmlLeakSite("sb_leaks", "ShadowByt3$", "http://sdwbyttda4uzwdffbt4m7niuodiwhcgmkyxqg5nly2bjxqa6xtbe3fyd.onion/leaks.php"),
    HtmlLeakSite("sarcoma", "Sarcoma", "http://sarcomawmawlhov7o5mdhz4eszxxlkyaoiyiy2b5iwxnds2dmb4jakad.onion/"),
    HtmlLeakSite("pear_ransomware", "PEAR Ransomware", "http://peargxn3oki34c4savcbcfqofjjwjnnyrlrbszfv6ujlx36mhrh57did.onion/"),
    HtmlLeakSite("anubis", "Anubis", "http://om6q4a6cyipxvt7ioudxt24cw4oqu4yodmqzl25mqd2hgllymrgu4aqd.onion/"),
)

SITE_BY_SLUG = {site.slug: site for site in HTML_LEAK_SITES}
