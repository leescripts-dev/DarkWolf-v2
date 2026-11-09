import requests

TOR_PROXY = "socks5h://127.0.0.1:9050"


def main():
    url = "https://check.torproject.org/api/ip"

    proxies = {
        "http": TOR_PROXY,
        "https": TOR_PROXY,
    }

    response = requests.get(
        url,
        proxies=proxies,
        timeout=30,
    )

    print(response.json())


if __name__ == "__main__":
    main()