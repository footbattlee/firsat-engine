from creative.generate_deal_creative import money


def main():
    assert money("1959.00") == "1.959 TL"
    assert money("1123.20") == "1.123,20 TL"
    assert money("849.90") == "849,90 TL"
    print("FORMAT TEST OK")


if __name__ == "__main__":
    main()
