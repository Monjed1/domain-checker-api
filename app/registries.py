from dataclasses import dataclass


@dataclass(frozen=True)
class TldRegistry:
    """Per-TLD registry endpoints (used when IANA RDAP bootstrap has no entry)."""

    whois_host: str | None = None
    whois_query: str = "{domain}"
    rdap_urls: tuple[str, ...] = ()
    extra_available_patterns: tuple[str, ...] = ()


# ccTLDs and others often missing or incomplete in IANA RDAP bootstrap.
TLD_REGISTRIES: dict[str, TldRegistry] = {
    "it": TldRegistry(
        whois_host="whois.nic.it",
        rdap_urls=("https://rdap.nic.it",),
        extra_available_patterns=(
            r"status:\s*available",
            r"domain available",
            r"available for registration",
            r"non registrato",
            r"dominio disponibile",
            r"dominio libero",
        ),
    ),
    "de": TldRegistry(
        whois_host="whois.denic.de",
        whois_query="-T dn {domain}",
        extra_available_patterns=(r"status:\s*free",),
    ),
    "fr": TldRegistry(
        whois_host="whois.nic.fr",
        rdap_urls=("https://rdap.nic.fr",),
        extra_available_patterns=(r"status:\s*not in use", r"status:\s*free"),
    ),
    "es": TldRegistry(
        whois_host="whois.nic.es",
        rdap_urls=("https://rdap.nic.es",),
        extra_available_patterns=(r"libre", r"status:\s*free"),
    ),
    "nl": TldRegistry(whois_host="whois.domain-registry.nl"),
    "be": TldRegistry(whois_host="whois.dns.be"),
    "eu": TldRegistry(
        whois_host="whois.eu",
        rdap_urls=("https://rdap.eu.org",),
    ),
    "pt": TldRegistry(whois_host="whois.dns.pt"),
    "pl": TldRegistry(whois_host="whois.dns.pl"),
    "ch": TldRegistry(whois_host="whois.nic.ch", rdap_urls=("https://rdap.nic.ch",)),
    "li": TldRegistry(whois_host="whois.nic.ch", rdap_urls=("https://rdap.nic.ch",)),
    "at": TldRegistry(whois_host="whois.nic.at"),
    "fi": TldRegistry(whois_host="whois.fi"),
    "se": TldRegistry(whois_host="whois.iis.se"),
    "no": TldRegistry(
        whois_host="whois.norid.no",
        rdap_urls=("https://rdap.norid.no",),
    ),
    "dk": TldRegistry(whois_host="whois.dk-hostmaster.dk"),
    "cz": TldRegistry(whois_host="whois.nic.cz"),
    "sk": TldRegistry(whois_host="whois.sk-nic.sk"),
    "ro": TldRegistry(whois_host="whois.rotld.ro"),
    "hu": TldRegistry(whois_host="whois.nic.hu"),
    "gr": TldRegistry(whois_host="whois.ics.forth.gr"),
    "ie": TldRegistry(whois_host="whois.domainregistry.ie"),
    "uk": TldRegistry(whois_host="whois.nominet.uk"),
    "co.uk": TldRegistry(whois_host="whois.nominet.uk"),
    "org.uk": TldRegistry(whois_host="whois.nominet.uk"),
    "me.uk": TldRegistry(whois_host="whois.nominet.uk"),
    "au": TldRegistry(whois_host="whois.auda.org.au"),
    "com.au": TldRegistry(whois_host="whois.auda.org.au"),
    "nz": TldRegistry(whois_host="whois.srs.net.nz"),
    "co.nz": TldRegistry(whois_host="whois.srs.net.nz"),
    "br": TldRegistry(whois_host="whois.registro.br"),
    "mx": TldRegistry(whois_host="whois.mx"),
    "jp": TldRegistry(whois_host="whois.jprs.jp"),
    "kr": TldRegistry(whois_host="whois.kr"),
    "in": TldRegistry(whois_host="whois.registry.in"),
    "tr": TldRegistry(whois_host="whois.trabis.gov.tr"),
    "ru": TldRegistry(whois_host="whois.tcinet.ru"),
    "ua": TldRegistry(whois_host="whois.ua"),
    "ca": TldRegistry(whois_host="whois.cira.ca"),
    "us": TldRegistry(whois_host="whois.nic.us"),
    "io": TldRegistry(whois_host="whois.nic.io"),
    "co": TldRegistry(whois_host="whois.nic.co"),
    "ai": TldRegistry(whois_host="whois.nic.ai"),
    "tv": TldRegistry(whois_host="whois.tv"),
    "me": TldRegistry(whois_host="whois.nic.me"),
    "cc": TldRegistry(whois_host="whois.nic.cc"),
    "xyz": TldRegistry(whois_host="whois.nic.xyz"),
}


def registry_for_tld(tld: str) -> TldRegistry | None:
    key = tld.lower().lstrip(".")
    return TLD_REGISTRIES.get(key)
